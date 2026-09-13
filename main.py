"""
API de Cálculo de Frete - Correios de Cabo Verde (CCV)

Baseado no tarifário oficial em vigor desde 01/11/2024.
Fonte: https://correios.cv/os-ccv/governanca-coorporativa/precario

Executar localmente:
    uvicorn main:app --reload

Documentação Swagger (gerada automaticamente):
    http://localhost:8000/docs      (Swagger UI)
    http://localhost:8000/redoc     (ReDoc, alternativa)
    http://localhost:8000/openapi.json  (esquema cru)

Variáveis de ambiente (ver .env.example):
    ADMIN_API_KEY        — password/chave exigida nos endpoints /admin/*
    SUPABASE_URL          — URL do projeto Supabase (tem valor por omissão)
    SUPABASE_ANON_KEY     — chave pública, só leitura (tem valor por omissão)
    SUPABASE_SERVICE_KEY  — chave de serviço, obrigatória para escrever (sem omissão)
    CORS_ORIGINS          — origens permitidas, separadas por vírgula (omissão: "*")
"""

import math
import os
from typing import List, Optional

from dotenv import load_dotenv
from enum import Enum
from fastapi import Depends, FastAPI, File, HTTPException, Request, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

import db
from landing import PAGINA_INICIAL_HTML
from validation import comparar_tarifarios, validar_tarifario

load_dotenv()

# --------------------------------------------------------------------------
# Tarifário: cache em memória, alimentado a partir do Supabase
# --------------------------------------------------------------------------

_tarifario_cache: Optional[dict] = None


def obter_tarifario() -> dict:
    global _tarifario_cache
    if _tarifario_cache is None:
        _tarifario_cache = db.carregar_tarifario()
    return _tarifario_cache


def invalidar_cache_tarifario() -> None:
    """Usado pelos testes para forçar uma releitura na próxima chamada."""
    global _tarifario_cache
    _tarifario_cache = None


# --------------------------------------------------------------------------
# Aplicação, CORS e rate limiting
# --------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="API de Frete — Correios de Cabo Verde (CCV)",
    description="""
Calculadora de tarifas postais dos **Correios de Cabo Verde, S.A.** (CCV),
pensada para ser integrada no checkout de lojas online cabo-verdianas.

## Como funciona

Os preços vêm de uma base de dados estruturada (Supabase) extraída do
tarifário oficial em PDF publicado pelos CCV. A tabela em vigor cobre todo
o arquipélago com o mesmo preço por escalão de peso: não existe
diferenciação por ilha de origem ou destino.

## Erros

Todos os erros seguem o formato `{"detail": "mensagem"}`. Códigos usados:
`404`, `422`, `401`, `409` (variações de preço suspeitas), `429`, `500`.

## Limites de pedidos

Endpoints públicos: 30 pedidos/minuto por IP. Endpoints de administração:
10 pedidos/minuto por IP. Em serverless com múltiplas instâncias, este
limite é por instância (memória local, não partilhada).

## Administração (`/admin/*`)

Requerem `X-API-Key`. O novo tarifário é validado (preços positivos,
escalões coerentes) e comparado com o atual — variações ≥20% bloqueiam a
aplicação a menos que `forcar: true`.
""",
    version="0.3.0",
    contact={"name": "Tarifário oficial dos CCV", "url": "https://correios.cv/os-ccv/governanca-coorporativa/precario"},
    openapi_tags=[
        {"name": "Metadados", "description": "Estado do serviço e informação de referência."},
        {"name": "Frete", "description": "Cálculo de custos de envio. Sem autenticação."},
        {"name": "Administração", "description": "Atualização do tarifário. Requer X-API-Key."},
    ],
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Mantém o mesmo formato {"detail": ...} usado em todos os outros erros da API."""
    return JSONResponse(status_code=429, content={"detail": f"Limite de pedidos excedido ({exc.detail}). Tenta novamente dentro de instantes."})


# Nota: não usamos SlowAPIMiddleware (baseado em BaseHTTPMiddleware) — em
# combinação com o handler genérico de exceções abaixo, isso impedia esse
# handler de ser acionado (interação conhecida do Starlette com
# BaseHTTPMiddleware). O decorador @limiter.limit em cada endpoint já é
# suficiente para aplicar os limites.

_cors_origins_env = os.getenv("CORS_ORIGINS", "*")
_cors_origins = ["*"] if _cors_origins_env.strip() == "*" else [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def erro_inesperado_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Erro interno inesperado."})


# --------------------------------------------------------------------------
# Autenticação dos endpoints /admin
# --------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def exigir_api_key(chave: Optional[str] = Security(_api_key_header)) -> None:
    chave_esperada = os.getenv("ADMIN_API_KEY")
    if not chave_esperada:
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY não está configurada no servidor.")
    if not chave or chave != chave_esperada:
        raise HTTPException(status_code=401, detail="Chave de API inválida ou em falta (cabeçalho X-API-Key).")


# --------------------------------------------------------------------------
# Modelos
# --------------------------------------------------------------------------

class Destino(str, Enum):
    nacional = "nacional"
    internacional = "internacional"


class TipoCorrespondencia(str, Enum):
    correspondencia = "correspondencia"
    impressos_vulgares = "impressos_vulgares"
    jornais_e_publicacoes_periodicas = "jornais_e_publicacoes_periodicas"
    pacotes_postais = "pacotes_postais"


class ServicoCorreio(str, Enum):
    correio_normal = "correio_normal"
    correio_azul = "correio_azul"


class ErroResposta(BaseModel):
    detail: str = Field(..., description="Mensagem legível a explicar o que correu mal.")

    model_config = ConfigDict(json_schema_extra={"example": {"detail": "Nenhuma opção de envio encontrada para este peso/destino."}})


class OpcaoFrete(BaseModel):
    servico: str = Field(..., json_schema_extra={"example": "Encomendas E-commerce"})
    categoria: str = Field(..., json_schema_extra={"example": "Normal"})
    faixa_peso_g: str = Field(..., json_schema_extra={"example": "501-1000g"})
    preco: float = Field(..., json_schema_extra={"example": 399})
    moeda: str = Field("CVE")
    observacao: Optional[str] = None


class CalculoEncomendaRequest(BaseModel):
    peso_g: int = Field(..., gt=0, le=20000)
    destino: Destino = Field(Destino.nacional)

    model_config = ConfigDict(json_schema_extra={"example": {"peso_g": 1200, "destino": "nacional"}})


class CalculoEncomendaResponse(BaseModel):
    peso_g: int
    destino: Destino
    opcoes: List[OpcaoFrete]


class CalculoCorrespondenciaRequest(BaseModel):
    peso_g: int = Field(..., gt=0, le=2000)
    destino: Destino = Field(Destino.nacional)
    servico: ServicoCorreio = Field(ServicoCorreio.correio_normal)
    tipo: TipoCorrespondencia = Field(TipoCorrespondencia.correspondencia)

    model_config = ConfigDict(json_schema_extra={"example": {"peso_g": 300, "destino": "nacional", "servico": "correio_normal", "tipo": "correspondencia"}})


class CalculoCorrespondenciaResponse(BaseModel):
    peso_g: int
    destino: Destino
    opcao: OpcaoFrete


class ComparacaoItem(BaseModel):
    secao: str
    categoria: str
    de_g: Optional[int] = None
    ate_g: Optional[int] = None
    tipo: str
    campo: Optional[str] = None
    preco_atual: Optional[float] = None
    preco_novo: Optional[float] = None
    variacao_pct: Optional[float] = None
    suspeito: bool


class ExtracaoTarifarioResponse(BaseModel):
    avisos: List[str] = Field(default_factory=list)
    tarifa_produtos_bruto: List[str]
    tarifario_extraido: dict
    comparacao_com_atual: List[ComparacaoItem] = Field(default_factory=list)


class AplicarTarifarioRequest(BaseModel):
    tarifario: dict
    forcar: bool = False


class AplicarTarifarioResponse(BaseModel):
    mensagem: str
    atualizado_em: str
    comparacao: List[ComparacaoItem] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    versao: str
    tarifario_carregado: bool
    supabase_acessivel: bool


# --------------------------------------------------------------------------
# Funções de lookup
# --------------------------------------------------------------------------

def _match(peso_g: int, faixa: dict) -> bool:
    minimo = faixa.get("de_g", 0)
    maximo = faixa.get("ate_g")
    return maximo is not None and minimo <= peso_g <= maximo


def buscar_encomenda_ecommerce(tarifario: dict, peso_g: int, destino: Destino) -> List[OpcaoFrete]:
    if destino != Destino.nacional:
        return []
    return [
        OpcaoFrete(
            servico="Encomendas E-commerce", categoria="Normal",
            faixa_peso_g=f"{faixa.get('de_g', 0)}-{faixa['ate_g']}g", preco=faixa["preco"],
        )
        for faixa in tarifario["encomendas_ecommerce"]["modalidade_normal"]
        if _match(peso_g, faixa)
    ]


def buscar_encomendas_postais(tarifario: dict, peso_g: int, destino: Destino) -> List[OpcaoFrete]:
    if destino != Destino.nacional:
        return []
    nomes = {
        "regime_nacional_entrega_balcao": "Entrega ao Balcão",
        "regime_nacional_entrega_domicilio": "Entrega ao Domicílio",
        "regime_nacional_recolha_e_entrega_domicilio": "Recolha e Entrega ao Domicílio",
    }
    opcoes = []
    for chave, nome in nomes.items():
        for faixa in tarifario["encomendas_postais"][chave]:
            if _match(peso_g, faixa):
                opcoes.append(OpcaoFrete(
                    servico="Encomendas Postais", categoria=nome,
                    faixa_peso_g=f"{faixa.get('de_g', 0)}-{faixa['ate_g']}g", preco=faixa["preco"],
                ))
    return opcoes


def buscar_correio_expresso(tarifario: dict, peso_g: int, destino: Destino) -> List[OpcaoFrete]:
    dados = tarifario["correio_expresso_ems"]
    escaloes = dados["escaloes"]
    limite_superior = escaloes[-1]["ate_g"]

    if peso_g <= limite_superior:
        for faixa in escaloes:
            if _match(peso_g, faixa):
                return [OpcaoFrete(
                    servico="Correio Expresso (EMS)", categoria="Standard",
                    faixa_peso_g=f"{faixa.get('de_g', 0)}-{faixa['ate_g']}g", preco=faixa[destino.value],
                )]
        return []

    fracao_g = dados["fracao_adicional_g"]
    preco_fracao = dados["preco_fracao_adicional"][destino.value]
    preco_base = escaloes[-1][destino.value]
    excedente = peso_g - limite_superior
    n_fracoes = math.ceil(excedente / fracao_g)
    preco_total = preco_base + n_fracoes * preco_fracao
    return [OpcaoFrete(
        servico="Correio Expresso (EMS)", categoria="Standard",
        faixa_peso_g=f"acima de {limite_superior}g", preco=preco_total,
        observacao=f"Base ({limite_superior}g) + {n_fracoes} fração(ões) adicional(is) de {fracao_g}g",
    )]


def buscar_correio(tarifario: dict, peso_g: int, destino: Destino, servico: ServicoCorreio, tipo: TipoCorrespondencia) -> OpcaoFrete:
    tabela = tarifario[servico.value][tipo.value]
    for faixa in tabela:
        if _match(peso_g, faixa):
            return OpcaoFrete(
                servico=servico.value.replace("_", " ").title(),
                categoria=tipo.value.replace("_", " ").title(),
                faixa_peso_g=f"{faixa.get('de_g', 0)}-{faixa['ate_g']}g",
                preco=faixa[destino.value],
            )
    raise HTTPException(status_code=404, detail=f"Não existe escalão de tarifa para {peso_g}g neste serviço/categoria.")


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.get("/health", tags=["Metadados"], summary="Verifica o estado do serviço", response_model=HealthResponse)
def health():
    try:
        obter_tarifario()
        tarifario_ok = True
    except Exception:
        tarifario_ok = False
    supabase_ok = db.testar_ligacao()
    return HealthResponse(
        status="ok" if (tarifario_ok and supabase_ok) else "degradado",
        versao=app.version,
        tarifario_carregado=tarifario_ok,
        supabase_acessivel=supabase_ok,
    )


@app.get("/api/v1/servicos", tags=["Metadados"], summary="Lista os serviços e categorias disponíveis")
def listar_servicos():
    tarifario = obter_tarifario()
    return {
        "encomendas": ["encomendas_ecommerce (até 5.000g)", "encomendas_postais (até 20.000g)", "correio_expresso_ems (sem limite, com fração adicional)"],
        "correspondencia": {
            "servicos": [s.value for s in ServicoCorreio],
            "tipos": [t.value for t in TipoCorrespondencia],
            "limite_peso_g": 2000,
        },
        "destinos": [d.value for d in Destino],
        "fonte": tarifario.get("meta", {}).get("fonte"),
        "tarifario_em_vigor_desde": tarifario.get("meta", {}).get("data_entrada_em_vigor"),
    }


@app.post(
    "/api/v1/calcular-frete", tags=["Frete"],
    summary="Calcula o custo de envio de uma encomenda/pacote",
    response_model=CalculoEncomendaResponse,
    responses={
        404: {"model": ErroResposta},
        422: {"model": ErroResposta},
        429: {"model": ErroResposta},
    },
)
@limiter.limit("30/minute")
def calcular_frete_encomenda(request: Request, pedido: CalculoEncomendaRequest):
    tarifario = obter_tarifario()
    peso_g, destino = pedido.peso_g, pedido.destino

    opcoes = (
        buscar_encomenda_ecommerce(tarifario, peso_g, destino)
        + buscar_encomendas_postais(tarifario, peso_g, destino)
        + buscar_correio_expresso(tarifario, peso_g, destino)
    )
    opcoes.sort(key=lambda o: o.preco)

    if not opcoes:
        raise HTTPException(status_code=404, detail="Nenhuma opção de envio encontrada para este peso/destino.")

    return CalculoEncomendaResponse(peso_g=peso_g, destino=destino, opcoes=opcoes)


@app.post(
    "/api/v1/calcular-frete/correspondencia", tags=["Frete"],
    summary="Calcula o custo de envio de correspondência (cartas, impressos, jornais)",
    response_model=CalculoCorrespondenciaResponse,
    responses={
        404: {"model": ErroResposta},
        422: {"model": ErroResposta},
        429: {"model": ErroResposta},
    },
)
@limiter.limit("30/minute")
def calcular_frete_correspondencia(request: Request, pedido: CalculoCorrespondenciaRequest):
    tarifario = obter_tarifario()
    opcao = buscar_correio(tarifario, pedido.peso_g, pedido.destino, pedido.servico, pedido.tipo)
    return CalculoCorrespondenciaResponse(peso_g=pedido.peso_g, destino=pedido.destino, opcao=opcao)


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def raiz():
    return HTMLResponse(content=PAGINA_INICIAL_HTML)


# --------------------------------------------------------------------------
# Endpoints de administração
# --------------------------------------------------------------------------

@app.post(
    "/api/v1/admin/tarifario/extrair", tags=["Administração"],
    summary="[protegido] Extrai o tarifário de um novo PDF dos CCV para revisão",
    response_model=ExtracaoTarifarioResponse,
    dependencies=[Depends(exigir_api_key)],
    responses={401: {"model": ErroResposta}, 422: {"model": ErroResposta}, 429: {"model": ErroResposta}},
)
@limiter.limit("10/minute")
async def extrair_tarifario_de_pdf(request: Request, ficheiro: UploadFile = File(...)):
    if ficheiro.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=422, detail="O ficheiro enviado não parece ser um PDF.")

    import io
    from pdf_parser import extrair_tarifario

    conteudo = await ficheiro.read()
    try:
        resultado = extrair_tarifario(io.BytesIO(conteudo))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Falha ao processar o PDF: {exc}")

    try:
        tarifario_atual = obter_tarifario()
        comparacao = comparar_tarifarios(tarifario_atual, resultado["tarifario"])
    except Exception:
        comparacao = []

    return ExtracaoTarifarioResponse(
        avisos=resultado["avisos"],
        tarifa_produtos_bruto=resultado["tarifa_produtos_bruto"],
        tarifario_extraido=resultado["tarifario"],
        comparacao_com_atual=comparacao,
    )


@app.post(
    "/api/v1/admin/tarifario/aplicar", tags=["Administração"],
    summary="[protegido] Valida, compara e substitui o tarifário em produção",
    response_model=AplicarTarifarioResponse,
    dependencies=[Depends(exigir_api_key)],
    responses={401: {"model": ErroResposta}, 409: {"model": ErroResposta}, 422: {"model": ErroResposta}, 429: {"model": ErroResposta}},
)
@limiter.limit("10/minute")
def aplicar_tarifario(request: Request, pedido: AplicarTarifarioRequest):
    try:
        validado = validar_tarifario(pedido.tarifario)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Tarifário inválido: {exc.errors()}")

    tarifario_novo = validado.model_dump(exclude_none=True)
    tarifario_atual = obter_tarifario()
    comparacao = comparar_tarifarios(tarifario_atual, tarifario_novo)
    suspeitos = [c for c in comparacao if c["suspeito"]]

    if suspeitos and not pedido.forcar:
        raise HTTPException(
            status_code=409,
            detail={
                "mensagem": f"{len(suspeitos)} variação(ões) de preço suspeita(s) detetada(s). Reenvia com forcar=true para aplicar mesmo assim.",
                "comparacao": suspeitos,
            },
        )

    atualizado_em = db.gravar_tarifario(tarifario_novo)

    try:
        db.registar_auditoria(
            tarifario_anterior=tarifario_atual,
            tarifario_novo=tarifario_novo,
            comparacao=comparacao,
            avisos=[],
            origem="admin/tarifario/aplicar",
        )
    except Exception:
        pass

    global _tarifario_cache
    _tarifario_cache = tarifario_novo

    return AplicarTarifarioResponse(
        mensagem="Tarifário atualizado com sucesso." + (" (forçado apesar de variações suspeitas)" if suspeitos else ""),
        atualizado_em=atualizado_em,
        comparacao=comparacao,
    )
