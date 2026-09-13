"""
Cliente Supabase minimalista para a API de Frete CCV.

Usa apenas `httpx` (puro Python, sem componentes binários) a falar
diretamente com o REST autogerado do Supabase (PostgREST) — evita
bibliotecas de driver Postgres (psycopg2, asyncpg) que trazem extensões
compiladas e já tivemos problemas com esse tipo de dependência no runtime
serverless da Vercel (ver pdf_parser.py).

Tabelas usadas (projeto "kriolsync"):
  - ccv_tarifario            — linha única (id=1) com o tarifário atual em `dados` (jsonb)
  - ccv_tarifario_auditoria  — uma linha por cada substituição do tarifário
"""

import os
from datetime import datetime, timezone
from typing import Optional

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ispblrbswkvvkwoeripg.supabase.co")

# Chave pública (anon) — segura para expor, só permite leitura (ver políticas RLS).
# Pode ser sobreposta por variável de ambiente, mas tem um valor por omissão
# para que a leitura funcione mesmo sem configuração extra.
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlzcGJscmJzd2t2dmt3b2VyaXBnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzY3Mzg3NjAsImV4cCI6MjA1MjMxNDc2MH0.Qe7wPCsjqMWgHv-yYKTNhBo0468pGldgymGzOYqYks8",
)

# Chave de serviço — NUNCA tem valor por omissão. Necessária para escrever
# (aplicar tarifário, registar auditoria). Configurar em .env / Vercel env vars.
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

REST_URL = f"{SUPABASE_URL}/rest/v1"

_TIMEOUT = 10.0


class SupabaseConfigError(RuntimeError):
    """A chave de serviço não está configurada quando era necessária para escrever."""


def _headers(usar_service_key: bool = False) -> dict:
    chave = SUPABASE_SERVICE_KEY if usar_service_key else SUPABASE_ANON_KEY
    if usar_service_key and not chave:
        raise SupabaseConfigError(
            "SUPABASE_SERVICE_KEY não está configurada no servidor — "
            "necessária para atualizar o tarifário. Define-a nas variáveis de ambiente."
        )
    return {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
    }


def carregar_tarifario() -> dict:
    """Lê o tarifário atual (linha id=1) usando a chave pública (só leitura)."""
    r = httpx.get(
        f"{REST_URL}/ccv_tarifario",
        params={"id": "eq.1", "select": "dados,atualizado_em"},
        headers=_headers(usar_service_key=False),
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    linhas = r.json()
    if not linhas:
        raise RuntimeError(
            "Tarifário não encontrado na base de dados (linha id=1 em falta em ccv_tarifario)."
        )
    return linhas[0]["dados"]


def gravar_tarifario(novo_tarifario: dict) -> str:
    """Substitui o tarifário (upsert na linha id=1). Devolve o timestamp gravado."""
    agora = datetime.now(timezone.utc).isoformat()
    r = httpx.post(
        f"{REST_URL}/ccv_tarifario",
        headers={**_headers(usar_service_key=True), "Prefer": "resolution=merge-duplicates"},
        json=[{"id": 1, "dados": novo_tarifario, "atualizado_em": agora}],
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return agora


def registar_auditoria(
    tarifario_anterior: Optional[dict],
    tarifario_novo: dict,
    comparacao: list,
    avisos: list,
    origem: str,
) -> None:
    """Regista uma entrada de auditoria — quem/quando/o que mudou."""
    r = httpx.post(
        f"{REST_URL}/ccv_tarifario_auditoria",
        headers=_headers(usar_service_key=True),
        json=[{
            "tarifario_anterior": tarifario_anterior,
            "tarifario_novo": tarifario_novo,
            "comparacao": comparacao,
            "avisos": avisos,
            "origem": origem,
        }],
        timeout=_TIMEOUT,
    )
    r.raise_for_status()


def testar_ligacao() -> bool:
    """Usado pelo /health — confirma que o Supabase responde, sem expor detalhes internos."""
    try:
        r = httpx.get(
            f"{REST_URL}/ccv_tarifario",
            params={"id": "eq.1", "select": "id"},
            headers=_headers(usar_service_key=False),
            timeout=5.0,
        )
        return r.status_code == 200
    except Exception:
        return False
