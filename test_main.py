"""
Testes automatizados da API de Frete CCV.

Correr com:
    pytest -v

O Supabase é sempre mockado (via monkeypatch) — estes testes não fazem
nenhuma chamada de rede real, para poderem correr em qualquer máquina/CI
sem precisar de credenciais.
"""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main

TARIFARIO_PATH = Path(__file__).parent / "tarifario_ccv.json"
ADMIN_KEY = "chave-de-teste"


@pytest.fixture
def tarifario_base() -> dict:
    with open(TARIFARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def store(tarifario_base, monkeypatch):
    """Substitui as funções de acesso ao Supabase por um "banco" em memória."""
    estado = {"tarifario": copy.deepcopy(tarifario_base), "auditoria": []}

    def fake_carregar():
        return estado["tarifario"]

    def fake_gravar(novo):
        estado["tarifario"] = novo
        return datetime.now(timezone.utc).isoformat()

    def fake_auditoria(**kwargs):
        estado["auditoria"].append(kwargs)

    def fake_testar_ligacao():
        return True

    monkeypatch.setattr(main.db, "carregar_tarifario", fake_carregar)
    monkeypatch.setattr(main.db, "gravar_tarifario", fake_gravar)
    monkeypatch.setattr(main.db, "registar_auditoria", fake_auditoria)
    monkeypatch.setattr(main.db, "testar_ligacao", fake_testar_ligacao)
    main.invalidar_cache_tarifario()
    main.limiter.reset()

    yield estado

    main.invalidar_cache_tarifario()
    main.limiter.reset()


@pytest.fixture
def client(store):
    import os
    os.environ["ADMIN_API_KEY"] = ADMIN_KEY
    return TestClient(main.app, raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Página inicial
# --------------------------------------------------------------------------

def test_pagina_inicial_serve_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "calc-form" in r.text


# --------------------------------------------------------------------------
# /health
# --------------------------------------------------------------------------

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# --------------------------------------------------------------------------
# /api/v1/calcular-frete
# --------------------------------------------------------------------------

@pytest.mark.parametrize("peso_g,destino,esperado_min_opcoes", [
    (1, "nacional", 1),
    (500, "nacional", 1),      # fronteira exata do 1o escalao do e-commerce
    (501, "nacional", 1),      # logo a seguir à fronteira
    (5000, "nacional", 1),     # limite superior do e-commerce
    (20000, "nacional", 1),    # limite superior das encomendas postais
    (2500, "nacional", 1),     # acima do limite do EMS -> fracao adicional
])
def test_calcular_frete_casos_validos(client, peso_g, destino, esperado_min_opcoes):
    r = client.post("/api/v1/calcular-frete", json={"peso_g": peso_g, "destino": destino})
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo["opcoes"]) >= esperado_min_opcoes
    precos = [o["preco"] for o in corpo["opcoes"]]
    assert precos == sorted(precos)  # confirma que vem ordenado


def test_calcular_frete_peso_zero_e_rejeitado(client):
    r = client.post("/api/v1/calcular-frete", json={"peso_g": 0, "destino": "nacional"})
    assert r.status_code == 422


def test_calcular_frete_peso_acima_do_limite_e_rejeitado(client):
    r = client.post("/api/v1/calcular-frete", json={"peso_g": 99999, "destino": "nacional"})
    assert r.status_code == 422


def test_calcular_frete_destino_invalido(client):
    r = client.post("/api/v1/calcular-frete", json={"peso_g": 500, "destino": "marte"})
    assert r.status_code == 422


def test_calcular_frete_fracao_adicional_ems(client):
    r = client.post("/api/v1/calcular-frete", json={"peso_g": 2500, "destino": "nacional"})
    assert r.status_code == 200
    ems = [o for o in r.json()["opcoes"] if o["servico"] == "Correio Expresso (EMS)"][0]
    # base (1000g, 1500 CVE) + 3 fracoes de 500g (350 CVE cada) = 1500 + 1050 = 2550
    assert ems["preco"] == 1500 + 3 * 350


# --------------------------------------------------------------------------
# /api/v1/calcular-frete/correspondencia
# --------------------------------------------------------------------------

def test_calcular_correspondencia_ok(client):
    r = client.post("/api/v1/calcular-frete/correspondencia", json={
        "peso_g": 300, "destino": "nacional", "servico": "correio_normal", "tipo": "correspondencia",
    })
    assert r.status_code == 200
    assert r.json()["opcao"]["preco"] == 320


def test_calcular_correspondencia_peso_acima_do_limite(client):
    r = client.post("/api/v1/calcular-frete/correspondencia", json={"peso_g": 5000, "destino": "nacional"})
    assert r.status_code == 422


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------

def test_cors_preflight(client):
    r = client.options(
        "/api/v1/calcular-frete",
        headers={"Origin": "https://loja-exemplo.cv", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


# --------------------------------------------------------------------------
# Autenticação /admin
# --------------------------------------------------------------------------

def test_admin_sem_chave_e_recusado(client):
    r = client.post("/api/v1/admin/tarifario/aplicar", json={"tarifario": {}})
    assert r.status_code == 401


def test_admin_com_chave_errada_e_recusado(client):
    r = client.post("/api/v1/admin/tarifario/aplicar", json={"tarifario": {}}, headers={"X-API-Key": "errada"})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Validação rigorosa + comparação automática (aplicar tarifário)
# --------------------------------------------------------------------------

def test_aplicar_tarifario_secao_em_falta(client, tarifario_base):
    incompleto = {k: v for k, v in tarifario_base.items() if k != "encomendas_postais"}
    r = client.post(
        "/api/v1/admin/tarifario/aplicar",
        json={"tarifario": incompleto},
        headers={"X-API-Key": ADMIN_KEY},
    )
    assert r.status_code == 422


def test_aplicar_tarifario_preco_negativo(client, tarifario_base):
    mau = copy.deepcopy(tarifario_base)
    mau["encomendas_ecommerce"]["modalidade_normal"][0]["preco"] = -50
    r = client.post("/api/v1/admin/tarifario/aplicar", json={"tarifario": mau}, headers={"X-API-Key": ADMIN_KEY})
    assert r.status_code == 422


def test_aplicar_tarifario_escalao_invertido(client, tarifario_base):
    mau = copy.deepcopy(tarifario_base)
    mau["encomendas_ecommerce"]["modalidade_normal"][0]["de_g"] = 999999
    r = client.post("/api/v1/admin/tarifario/aplicar", json={"tarifario": mau}, headers={"X-API-Key": ADMIN_KEY})
    assert r.status_code == 422


def test_aplicar_tarifario_variacao_suspeita_bloqueia_sem_forcar(client, tarifario_base, store):
    suspeito = copy.deepcopy(tarifario_base)
    suspeito["encomendas_ecommerce"]["modalidade_normal"][0]["preco"] *= 3  # +200%

    r = client.post("/api/v1/admin/tarifario/aplicar", json={"tarifario": suspeito}, headers={"X-API-Key": ADMIN_KEY})
    assert r.status_code == 409
    assert len(r.json()["detail"]["comparacao"]) >= 1
    # nao deve ter gravado
    assert store["tarifario"]["encomendas_ecommerce"]["modalidade_normal"][0]["preco"] == tarifario_base["encomendas_ecommerce"]["modalidade_normal"][0]["preco"]


def test_aplicar_tarifario_com_forcar_grava_e_regista_auditoria(client, tarifario_base, store):
    suspeito = copy.deepcopy(tarifario_base)
    suspeito["encomendas_ecommerce"]["modalidade_normal"][0]["preco"] *= 3

    r = client.post(
        "/api/v1/admin/tarifario/aplicar",
        json={"tarifario": suspeito, "forcar": True},
        headers={"X-API-Key": ADMIN_KEY},
    )
    assert r.status_code == 200
    assert store["tarifario"]["encomendas_ecommerce"]["modalidade_normal"][0]["preco"] == suspeito["encomendas_ecommerce"]["modalidade_normal"][0]["preco"]
    assert len(store["auditoria"]) == 1


def test_aplicar_tarifario_atualiza_cache_de_imediato(client, tarifario_base):
    novo = copy.deepcopy(tarifario_base)
    novo["encomendas_ecommerce"]["modalidade_normal"][0]["preco"] = 210  # variacao pequena (~5.5%), nao suspeita

    r = client.post("/api/v1/admin/tarifario/aplicar", json={"tarifario": novo}, headers={"X-API-Key": ADMIN_KEY})
    assert r.status_code == 200

    r2 = client.post("/api/v1/calcular-frete", json={"peso_g": 400, "destino": "nacional"})
    precos = [o["preco"] for o in r2.json()["opcoes"] if o["servico"] == "Encomendas E-commerce"]
    assert precos == [210]


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------

def test_rate_limit_calcular_frete(client):
    respostas = [
        client.post("/api/v1/calcular-frete", json={"peso_g": 500, "destino": "nacional"}).status_code
        for _ in range(31)
    ]
    assert respostas.count(200) == 30
    assert respostas.count(429) == 1


# --------------------------------------------------------------------------
# Handler de erro global
# --------------------------------------------------------------------------

def test_erro_inesperado_devolve_json_consistente(client, monkeypatch):
    def falha():
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(main.db, "carregar_tarifario", falha)
    main.invalidar_cache_tarifario()

    r = client.post("/api/v1/calcular-frete", json={"peso_g": 500, "destino": "nacional"})
    assert r.status_code == 500
    assert r.json() == {"detail": "Erro interno inesperado."}
