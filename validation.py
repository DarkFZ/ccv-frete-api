"""
Validação rigorosa da estrutura do tarifário e comparação automática entre
o tarifário atual e um novo tarifário (tipicamente extraído de um PDF),
para sinalizar variações de preço suspeitas antes de serem aplicadas.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

LIMIAR_VARIACAO_SUSPEITA_PCT = 20.0


# --------------------------------------------------------------------------
# Modelos de validação (rejeitam preços <= 0, escalões invertidos, etc.)
# --------------------------------------------------------------------------

class FaixaNacIntl(BaseModel):
    de_g: Optional[int] = Field(None, ge=0)
    ate_g: int = Field(..., gt=0)
    nacional: float = Field(..., gt=0)
    internacional: float = Field(..., gt=0)
    nota: Optional[str] = None

    @model_validator(mode="after")
    def _checar_intervalo(self):
        minimo = self.de_g or 0
        if self.ate_g <= minimo:
            raise ValueError(f"ate_g ({self.ate_g}) tem de ser maior que de_g ({minimo})")
        return self


class FaixaPreco(BaseModel):
    de_g: Optional[int] = Field(None, ge=0)
    ate_g: int = Field(..., gt=0)
    preco: float = Field(..., gt=0)

    @model_validator(mode="after")
    def _checar_intervalo(self):
        minimo = self.de_g or 0
        if self.ate_g <= minimo:
            raise ValueError(f"ate_g ({self.ate_g}) tem de ser maior que de_g ({minimo})")
        return self


class CorreioCategoria(BaseModel):
    correspondencia: List[FaixaNacIntl] = Field(default_factory=list)
    impressos_vulgares: List[FaixaNacIntl] = Field(default_factory=list)
    jornais_e_publicacoes_periodicas: List[FaixaNacIntl] = Field(default_factory=list)
    pacotes_postais: List[FaixaNacIntl] = Field(default_factory=list)
    nota: Optional[str] = None


class CorreioExpressoEms(BaseModel):
    escaloes: List[FaixaNacIntl] = Field(..., min_length=1)
    fracao_adicional_g: int = Field(..., gt=0)
    preco_fracao_adicional: Dict[str, float]

    @model_validator(mode="after")
    def _checar_precos_fracao(self):
        for chave in ("nacional", "internacional"):
            valor = self.preco_fracao_adicional.get(chave)
            if valor is None or valor <= 0:
                raise ValueError(f"preco_fracao_adicional.{chave} em falta ou inválido")
        return self


class EncomendasPostais(BaseModel):
    regime_nacional_entrega_balcao: List[FaixaPreco] = Field(..., min_length=1)
    regime_nacional_entrega_domicilio: List[FaixaPreco] = Field(..., min_length=1)
    regime_nacional_recolha_e_entrega_domicilio: List[FaixaPreco] = Field(..., min_length=1)


class EncomendasEcommerce(BaseModel):
    modalidade_normal: List[FaixaPreco] = Field(..., min_length=1)
    nota: Optional[str] = None

    model_config = ConfigDict(extra="allow")  # permite futuras modalidades (ex.: expresso) sem partir a validação


class TarifarioCompleto(BaseModel):
    """Esquema completo do tarifário — usado para validar antes de aplicar."""
    meta: Optional[dict] = None
    correio_normal: CorreioCategoria
    correio_azul: CorreioCategoria
    correio_expresso_ems: CorreioExpressoEms
    encomendas_postais: EncomendasPostais
    encomendas_ecommerce: EncomendasEcommerce
    tarifa_produtos: Optional[dict] = None  # secção solta, não validada ao detalhe

    model_config = ConfigDict(extra="allow")


def validar_tarifario(dados: dict) -> TarifarioCompleto:
    """
    Levanta pydantic.ValidationError (com mensagens detalhadas) se o
    tarifário não tiver a forma esperada ou contiver valores impossíveis
    (preços <= 0, escalões de peso invertidos, secções obrigatórias em falta).
    """
    return TarifarioCompleto.model_validate(dados)


# --------------------------------------------------------------------------
# Comparação automática — sinaliza variações de preço suspeitas
# --------------------------------------------------------------------------

def _achatar_precos(tarifario: dict) -> Dict[tuple, dict]:
    """Devolve {(secção, subchave, de_g, ate_g): {"nacional":.., "internacional":..} ou {"preco":..}}."""
    plano: Dict[tuple, dict] = {}

    for secao in ("correio_normal", "correio_azul"):
        bloco = tarifario.get(secao) or {}
        for sub, faixas in bloco.items():
            if not isinstance(faixas, list):
                continue
            for f in faixas:
                chave = (secao, sub, f.get("de_g", 0), f.get("ate_g"))
                plano[chave] = {"nacional": f.get("nacional"), "internacional": f.get("internacional")}

    ems = tarifario.get("correio_expresso_ems") or {}
    for f in ems.get("escaloes", []):
        chave = ("correio_expresso_ems", "escaloes", f.get("de_g", 0), f.get("ate_g"))
        plano[chave] = {"nacional": f.get("nacional"), "internacional": f.get("internacional")}
    if ems.get("preco_fracao_adicional"):
        plano[("correio_expresso_ems", "fracao_adicional", None, None)] = dict(ems["preco_fracao_adicional"])

    postais = tarifario.get("encomendas_postais") or {}
    for regime, faixas in postais.items():
        if not isinstance(faixas, list):
            continue
        for f in faixas:
            chave = ("encomendas_postais", regime, f.get("de_g", 0), f.get("ate_g"))
            plano[chave] = {"preco": f.get("preco")}

    ecom = tarifario.get("encomendas_ecommerce") or {}
    for modalidade, faixas in ecom.items():
        if not isinstance(faixas, list):
            continue
        for f in faixas:
            chave = ("encomendas_ecommerce", modalidade, f.get("de_g", 0), f.get("ate_g"))
            plano[chave] = {"preco": f.get("preco")}

    return plano


def comparar_tarifarios(
    atual: dict,
    novo: dict,
    limiar_percentual: float = LIMIAR_VARIACAO_SUSPEITA_PCT,
) -> List[dict]:
    """
    Compara dois tarifários e devolve uma lista de alterações de preço,
    escalões novos e escalões removidos. Cada alteração de preço inclui a
    variação percentual e uma flag `suspeito` quando essa variação
    ultrapassa o limiar (por omissão, 20%) — pensado para chamar antes de
    `aplicar_tarifario`, para revisão humana.
    """
    plano_atual = _achatar_precos(atual)
    plano_novo = _achatar_precos(novo)
    alteracoes: List[dict] = []

    for chave, valores_novos in plano_novo.items():
        secao, sub, de_g, ate_g = chave
        valores_atuais = plano_atual.get(chave)

        if valores_atuais is None:
            alteracoes.append({
                "secao": secao, "categoria": sub, "de_g": de_g, "ate_g": ate_g,
                "tipo": "escalao_novo", "suspeito": False,
            })
            continue

        for campo, novo_valor in valores_novos.items():
            antigo_valor = valores_atuais.get(campo)
            if antigo_valor is None or novo_valor is None or antigo_valor == novo_valor:
                continue
            variacao_pct = ((novo_valor - antigo_valor) / antigo_valor) * 100 if antigo_valor else None
            alteracoes.append({
                "secao": secao, "categoria": sub, "de_g": de_g, "ate_g": ate_g,
                "campo": campo,
                "preco_atual": antigo_valor,
                "preco_novo": novo_valor,
                "variacao_pct": round(variacao_pct, 1) if variacao_pct is not None else None,
                "tipo": "preco_alterado",
                "suspeito": abs(variacao_pct) >= limiar_percentual if variacao_pct is not None else False,
            })

    for chave in plano_atual:
        if chave not in plano_novo:
            secao, sub, de_g, ate_g = chave
            alteracoes.append({
                "secao": secao, "categoria": sub, "de_g": de_g, "ate_g": ate_g,
                "tipo": "escalao_removido", "suspeito": True,
            })

    return alteracoes
