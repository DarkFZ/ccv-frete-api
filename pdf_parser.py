"""
Extrator do tarifário oficial dos CCV a partir do PDF publicado.

Usa `pypdf` (sem dependências obrigatórias — sem componentes binários) em vez
de `pdfplumber`, porque a cadeia de dependências do pdfplumber
(pdfminer.six -> cryptography, com uma extensão Rust) falha a correr no
runtime Python serverless da Vercel. O `pypdf` extrai o texto já em linhas
limpas (uma linha por linha do PDF), o que é suficiente para este documento:
cada linha de dados termina em um ou dois valores "1.234$00", e as linhas de
título/categoria não têm preço nenhum.

Estratégia: percorre as linhas do documento, de cima para baixo, mantendo um
"estado atual" (secção principal + categoria/regime/modalidade em curso).
Uma linha sem preço no fim é tratada como título de secção ou de categoria;
uma linha com um ou dois preços no fim é uma linha de dados.

Limitação assumida: o layout de "Tarifa de Produtos" (embalagens, envelopes
personalizados, postais) tem sub-cabeçalhos irregulares que variam mais entre
versões do documento. Em vez de arriscar mapear mal um preço nessa secção,
devolvemos as linhas em bruto para revisão manual — as secções que alimentam
o cálculo de frete (Correio Normal/Azul, Expresso, Encomendas Postais,
Encomendas E-commerce) são as que são automaticamente estruturadas.
"""

import re
import unicodedata
from typing import BinaryIO, Optional

from pypdf import PdfReader

_PRECO_RE = re.compile(r"\d[\d.]*\$\d+")
_BOILERPLATE_PREFIXES = (
    "data entrada em vigor",
    "direção comercial",
    "direcao comercial",
    "correios de cabo verde",
)


def _normalizar(texto: str) -> str:
    texto = (texto or "").strip().lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return texto


def _preco_para_numero(valor: Optional[str]) -> Optional[float]:
    if not valor:
        return None
    valor = valor.strip()
    m = re.match(r"([\d.]+)\$(\d+)", valor)
    if not m:
        return None
    return float(m.group(1).replace(".", ""))


def _faixa_peso(label: Optional[str]) -> Optional[dict]:
    if not label:
        return None
    label_low = label.lower()
    if "fra" in label_low and "adicional" in label_low:
        return {"tipo": "fracao_adicional"}
    nums = [int(n.replace(".", "")) for n in re.findall(r"\d[\d.]*\d|\d", label)]
    if len(nums) >= 2:
        return {"de_g": nums[0], "ate_g": nums[-1]}
    if len(nums) == 1:
        return {"ate_g": nums[0]}
    return None


def _mapear_chave_principal(heading: str) -> Optional[str]:
    h = heading.upper()
    if "CORREIO NORMAL" in h:
        return "correio_normal"
    if "CORREIO AZUL" in h:
        return "correio_azul"
    if "EXPRESSO" in h:
        return "correio_expresso_ems"
    if "ENCOMENDAS POSTAIS" in h:
        return "encomendas_postais"
    if "E-COMMERCE" in h or "ECOMMERCE" in h:
        return "encomendas_ecommerce"
    if "PRODUTOS" in h:
        return "tarifa_produtos"
    return None


def _mapear_regime(label_norm: str) -> Optional[str]:
    if "balcao" in label_norm:
        return "regime_nacional_entrega_balcao"
    if "recolha" in label_norm and "domicilio" in label_norm:
        return "regime_nacional_recolha_e_entrega_domicilio"
    if "domicilio" in label_norm:
        return "regime_nacional_entrega_domicilio"
    return None


_CATEGORIAS_CONHECIDAS = (
    "correspondencia", "impressos_vulgares",
    "jornais_e_publicacoes_periodicas", "pacotes_postais",
)


def _linhas_do_documento(arquivo: BinaryIO):
    reader = PdfReader(arquivo)
    for page in reader.pages:
        texto = page.extract_text() or ""
        for linha in texto.split("\n"):
            linha = linha.strip()
            if not linha:
                continue
            if any(linha.lower().startswith(p) for p in _BOILERPLATE_PREFIXES):
                continue
            yield linha


def extrair_tarifario(arquivo: BinaryIO) -> dict:
    """
    Lê um PDF de tarifário CCV e devolve:
      {
        "tarifario": { ...estrutura igual ao tarifario_ccv.json... },
        "avisos": [ "..." ],           # secções não mapeadas automaticamente
        "tarifa_produtos_bruto": [...] # linhas em bruto, para revisão manual
      }
    """
    resultado = {
        "correio_normal": {},
        "correio_azul": {},
        "correio_expresso_ems": {"escaloes": [], "fracao_adicional_g": 500, "preco_fracao_adicional": {}},
        "encomendas_postais": {},
        "encomendas_ecommerce": {},
    }
    avisos = []
    tarifa_produtos_bruto = []

    current_top: Optional[str] = None
    current_sub: Optional[str] = None
    current_modalidade: Optional[str] = None

    for linha in _linhas_do_documento(arquivo):
        if re.match(r"^TARIFA(:| DE)", linha.strip().upper()):
            current_top = _mapear_chave_principal(linha)
            current_sub = None
            current_modalidade = None
            if current_top is None:
                avisos.append(f"Título de secção não reconhecido: '{linha}'")
            continue

        if current_top == "tarifa_produtos":
            tarifa_produtos_bruto.append(linha)
            continue

        precos_encontrados = list(_PRECO_RE.finditer(linha))

        if not precos_encontrados:
            # Linha sem preço: título de categoria/regime/modalidade, ou
            # cabeçalho de colunas (ex.: "Nacional Internacional").
            if current_top in ("correio_normal", "correio_azul"):
                sem_colunas = re.sub(r"\b(nacional|internacional)\b", "", linha, flags=re.IGNORECASE).strip()
                categoria_norm = _normalizar(sem_colunas)
                if categoria_norm in _CATEGORIAS_CONHECIDAS:
                    current_sub = categoria_norm
                # se não reconhecida (ex.: linha vazia após remover colunas), ignora silenciosamente
            elif current_top == "encomendas_postais":
                regime = _mapear_regime(_normalizar(linha))
                if regime:
                    current_sub = regime
            elif current_top == "encomendas_ecommerce":
                candidato = _normalizar(linha)
                if candidato and candidato not in ("modalidade_de_entrega_peso_tarifa",):
                    current_modalidade = candidato
            continue

        # Linha de dados (tem 1 ou 2 preços no fim)
        precos = [_preco_para_numero(m.group(0)) for m in precos_encontrados]
        label = linha[: precos_encontrados[0].start()].strip()
        faixa = _faixa_peso(label)
        if not faixa:
            avisos.append(f"Não consegui interpretar a faixa de peso em: '{linha}' (secção={current_top})")
            continue

        if current_top in ("correio_normal", "correio_azul"):
            if not current_sub or len(precos) < 2:
                avisos.append(f"Linha de {current_top} sem categoria/preços completos: '{linha}'")
                continue
            resultado[current_top].setdefault(current_sub, []).append(
                {**faixa, "nacional": precos[0], "internacional": precos[1]}
            )

        elif current_top == "correio_expresso_ems":
            if len(precos) < 2:
                avisos.append(f"Linha de Correio Expresso sem os dois preços: '{linha}'")
                continue
            if faixa.get("tipo") == "fracao_adicional":
                resultado["correio_expresso_ems"]["preco_fracao_adicional"] = {
                    "nacional": precos[0], "internacional": precos[1],
                }
            else:
                resultado["correio_expresso_ems"]["escaloes"].append(
                    {**{k: v for k, v in faixa.items() if k != "tipo"}, "nacional": precos[0], "internacional": precos[1]}
                )

        elif current_top == "encomendas_postais":
            if not current_sub:
                avisos.append(f"Linha de Encomendas Postais sem regime identificado: '{linha}'")
                continue
            resultado["encomendas_postais"].setdefault(current_sub, []).append({**faixa, "preco": precos[0]})

        elif current_top == "encomendas_ecommerce":
            modalidade = current_modalidade or "normal"
            chave = f"modalidade_{modalidade}"
            resultado["encomendas_ecommerce"].setdefault(chave, []).append({**faixa, "preco": precos[0]})

        else:
            avisos.append(f"Linha de dados fora de qualquer secção reconhecida: '{linha}'")

    if not resultado["correio_expresso_ems"]["preco_fracao_adicional"]:
        avisos.append("Não foi encontrada a linha de 'fração adicional' do Correio Expresso — confirmar manualmente.")

    return {
        "tarifario": resultado,
        "avisos": avisos,
        "tarifa_produtos_bruto": tarifa_produtos_bruto,
    }

