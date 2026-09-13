# API de Frete — Correios de Cabo Verde (CCV)

Calculadora de tarifas postais dos **Correios de Cabo Verde, S.A.**, pensada
para ser integrada no checkout de lojas online cabo-verdianas. Documentação
interativa (Swagger) gerada automaticamente a partir do código — nada
escrito à mão em YAML.

Os preços vêm de uma base de dados estruturada (Supabase), extraída do
tarifário oficial publicado em PDF pelos CCV — **sem scraping** do
simulador web.

> **Nota importante sobre o tarifário:** os CCV cobram o mesmo preço por
> escalão de peso em todo o arquipélago — **não há diferenciação por ilha
> de origem/destino**. Por isso os endpoints só pedem peso e destino
> (nacional/internacional), não ilhas.

Fonte oficial do tarifário: https://correios.cv/os-ccv/governanca-coorporativa/precario

---

## Funcionalidades

- **Página inicial interativa** — a raiz (`/`) serve uma página HTML com
  uma calculadora ao vivo, exemplos de código e o estado do serviço (não
  só um JSON de boas-vindas).
- **Cálculo de frete** para encomendas (E-commerce, Encomendas Postais,
  Correio Expresso/EMS) e correspondência (Correio Normal/Azul), devolvendo
  todas as opções aplicáveis ordenadas por preço.
- **Atualização do tarifário a partir de um novo PDF** oficial dos CCV —
  extração automática, validação rigorosa, comparação de preços e aplicação
  controlada (protegida por API key).
- **Persistência em Supabase** — sem depender de um ficheiro local, que não
  sobrevive de forma fiável em ambientes serverless.
- **Auditoria** — cada atualização do tarifário fica registada (antes/depois,
  diferenças de preço, origem).
- **Validação rigorosa** do tarifário (preços positivos, escalões de peso
  coerentes) antes de qualquer atualização ser aceite.
- **Comparação automática** entre o tarifário atual e um novo — variações de
  preço ≥20% são sinalizadas como suspeitas e bloqueiam a atualização a
  menos que seja confirmada explicitamente.
- **CORS** configurável.
- **Rate limiting** (30 pedidos/min nos endpoints públicos, 10/min nos de
  administração).
- **Tratamento de erros consistente** — toda a API responde sempre no
  formato `{"detail": "..."}`, mesmo em falhas não previstas.
- **Testes automatizados** (pytest), sem dependência de rede — toda a
  camada Supabase é mockada.

## Índice

- [Arquitetura](#arquitetura)
- [Como correr localmente](#como-correr-localmente)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Endpoints](#endpoints)
- [Atualizar o tarifário a partir de um novo PDF](#atualizar-o-tarifário-a-partir-de-um-novo-pdf)
- [Testes](#testes)
- [Base de dados (Supabase)](#base-de-dados-supabase)
- [Deploy](#deploy)
- [Decisões técnicas e limitações conhecidas](#decisões-técnicas-e-limitações-conhecidas)

## Arquitetura

```
main.py         — aplicação FastAPI: endpoints, modelos, CORS, rate limiting,
                  tratamento de erros, cache do tarifário em memória
landing.py      — página inicial (HTML/CSS/JS num único ficheiro, sem build step)
db.py           — cliente Supabase (REST/PostgREST via httpx, sem drivers binários)
validation.py   — esquema Pydantic rigoroso do tarifário + comparação automática
pdf_parser.py   — extrai o tarifário de um PDF oficial dos CCV (via pypdf)
tarifario_ccv.json — cópia de referência do tarifário (a fonte de verdade é o Supabase)
test_main.py    — testes automatizados (pytest), com o Supabase totalmente mockado
```

A app **não usa `pdfplumber`** para ler PDFs, de propósito: a cadeia de
dependências do pdfplumber (`pdfminer.six` → `cryptography`, que tem uma
extensão binária em Rust) falha a correr no runtime Python serverless da
Vercel. `pypdf` não tem dependências obrigatórias e resolve o mesmo problema
por extração de texto linha a linha.

## Como correr localmente

```bash
git clone <url-deste-repositorio>
cd ccv-frete-api
pip install -r requirements-dev.txt   # inclui pytest
cp .env.example .env                  # depois edita e preenche as chaves
uvicorn main:app --reload
```

Depois abre:
- http://localhost:8000/docs — Swagger UI (interativo)
- http://localhost:8000/redoc — documentação alternativa (ReDoc)
- http://localhost:8000/health — estado do serviço

## Variáveis de ambiente

Ver `.env.example` para a lista completa e comentada. Resumo:

| Variável | Obrigatória? | Descrição |
|---|---|---|
| `ADMIN_API_KEY` | Sim (para `/admin/*`) | Chave exigida no cabeçalho `X-API-Key`. |
| `SUPABASE_URL` | Não (tem omissão) | URL do projeto Supabase. |
| `SUPABASE_ANON_KEY` | Não (tem omissão) | Chave pública, só leitura. |
| `SUPABASE_SERVICE_KEY` | Sim (para escrever) | Chave de serviço — nunca expor nem commitar. |
| `CORS_ORIGINS` | Não (omissão: `*`) | Origens autorizadas, separadas por vírgula. |

## Endpoints

| Método | Rota | Autenticação | Descrição |
|---|---|---|---|
| `GET` | `/health` | — | Estado do serviço (tarifário carregado, Supabase acessível). |
| `GET` | `/api/v1/servicos` | — | Lista serviços, categorias, destinos e limites de peso. |
| `POST` | `/api/v1/calcular-frete` | — | Calcula o custo de envio de uma encomenda. |
| `POST` | `/api/v1/calcular-frete/correspondencia` | — | Calcula o custo de correspondência (cartas, impressos, jornais). |
| `POST` | `/api/v1/admin/tarifario/extrair` | `X-API-Key` | Extrai um novo tarifário de um PDF, sem aplicar. |
| `POST` | `/api/v1/admin/tarifario/aplicar` | `X-API-Key` | Valida, compara e substitui o tarifário em produção. |

Exemplo de pedido:

```bash
curl -X POST 'http://localhost:8000/api/v1/calcular-frete' \
  -H 'Content-Type: application/json' \
  -d '{"peso_g": 1200, "destino": "nacional"}'
```

Ver a especificação completa (schemas, exemplos, códigos de erro) em `/docs`.

## Atualizar o tarifário a partir de um novo PDF

Fluxo pensado para quando os CCV publicarem uma nova versão do tarifário:

1. **Extrair** — envia o PDF:
   ```bash
   curl -X POST http://localhost:8000/api/v1/admin/tarifario/extrair \
     -H "X-API-Key: <a tua chave>" \
     -F "ficheiro=@novo_tarifario.pdf"
   ```
   Devolve a estrutura extraída, avisos de secções não reconhecidas, a
   secção "Tarifa de Produtos" em bruto (layout mais irregular, requer
   revisão manual) e uma **comparação automática** com o tarifário atual.

2. **Rever** — confirma os avisos e a comparação. Corrige à mão o que for
   preciso.

3. **Aplicar** — envia o JSON revisto:
   ```bash
   curl -X POST http://localhost:8000/api/v1/admin/tarifario/aplicar \
     -H "X-API-Key: <a tua chave>" -H "Content-Type: application/json" \
     -d '{"tarifario": { ... }, "forcar": false}'
   ```
   Se houver variações de preço ≥20% face ao tarifário atual, a API recusa
   com `409` e devolve a lista de alterações suspeitas — reenvia com
   `"forcar": true` depois de confirmares que estão corretas.

## Exemplos de consumo

**cURL**
```bash
curl -X POST 'https://SEU-DOMINIO/api/v1/calcular-frete' \
  -H 'Content-Type: application/json' \
  -d '{"peso_g": 1200, "destino": "nacional"}'
```

**JavaScript (fetch)**
```javascript
const resposta = await fetch('https://SEU-DOMINIO/api/v1/calcular-frete', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ peso_g: 1200, destino: 'nacional' }),
});
const dados = await resposta.json();
console.log(dados.opcoes); // opções ordenadas da mais barata para a mais cara
```

**Python (requests)**
```python
import requests

resposta = requests.post(
    "https://SEU-DOMINIO/api/v1/calcular-frete",
    json={"peso_g": 1200, "destino": "nacional"},
)
dados = resposta.json()
print(dados["opcoes"])
```

**PHP (cURL)**
```php
$ch = curl_init('https://SEU-DOMINIO/api/v1/calcular-frete');
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
    CURLOPT_POSTFIELDS => json_encode(['peso_g' => 1200, 'destino' => 'nacional']),
]);
$dados = json_decode(curl_exec($ch), true);
print_r($dados['opcoes']);
```

A resposta tem sempre a forma:
```json
{
  "peso_g": 1200,
  "destino": "nacional",
  "opcoes": [
    { "servico": "Encomendas E-commerce", "categoria": "Normal", "faixa_peso_g": "1001-2000g", "preco": 599.0, "moeda": "CVE", "observacao": null }
  ]
}
```

## Testes

```bash
pip install -r requirements-dev.txt
pytest -v
```

Os testes mockam por completo o Supabase (não fazem nenhuma chamada de
rede), por isso correm em qualquer máquina ou pipeline de CI sem precisar
de credenciais.

## Base de dados (Supabase)

Duas tabelas, prefixadas com `ccv_` para não colidir com outros projetos no
mesmo Supabase:

- **`ccv_tarifario`** — linha única (`id = 1`) com o tarifário atual em
  `dados` (jsonb).
- **`ccv_tarifario_auditoria`** — uma linha por cada substituição do
  tarifário, com o antes/depois, a comparação de preços e a origem.

RLS ativo em ambas: leitura pública (a API de cálculo não precisa de
autenticação), escrita restrita à `service_role` key.

## Deploy

Testado em [Vercel](https://vercel.com) (Python serverless functions), sem
`vercel.json` — `main.py` na raiz é detetado automaticamente. Configura as
variáveis de ambiente em *Project Settings → Environment Variables* (nunca
num `.env` commitado).

Para ligar a Vercel a este repositório em vez de fazer deploy manual de
ficheiros, importa o projeto diretamente do GitHub no dashboard da Vercel —
isso dá deploys automáticos a cada push e um domínio de produção fixo.

## Decisões técnicas e limitações conhecidas

- **Sem diferenciação por ilha** — o tarifário oficial não distingue rotas
  entre ilhas, só peso e nacional/internacional.
- **Sem prazos de entrega** — o tarifário oficial só tem preços; os prazos
  (dias úteis) têm de vir de outra fonte.
- **Rate limiting em memória** — em ambientes serverless com múltiplas
  instâncias, a contagem não é partilhada entre elas; sob tráfego
  concorrente elevado o limite real pode ser mais permissivo do que o
  configurado. Para um limite verdadeiramente distribuído seria necessário
  um backend partilhado (ex.: Redis/Upstash).
- **`pypdf` em vez de `pdfplumber`** — ver [Arquitetura](#arquitetura).
