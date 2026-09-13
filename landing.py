"""HTML da página inicial da API (servida em GET "/"). Ficheiro único,
sem build step — CSS e JS inline, pensado para continuar a funcionar como
função serverless simples."""

PAGINA_INICIAL_HTML = """<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>API de Frete — Correios de Cabo Verde</title>
<meta name="description" content="Calculadora de tarifas postais dos Correios de Cabo Verde (CCV) para integração em lojas online.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #f5f6fa;
    --ink: #0e1b33;
    --ink-soft: #4a5568;
    --blue: #1b3f94;
    --blue-dark: #142f70;
    --red: #ce1126;
    --gold: #f4c400;
    --card: #ffffff;
    --border: #dde1ec;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: 'Inter', system-ui, sans-serif;
    line-height: 1.5;
  }
  h1, h2, h3, .display {
    font-family: 'Space Grotesk', 'Inter', sans-serif;
    font-weight: 700;
    letter-spacing: -0.01em;
  }
  code, pre, .mono {
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
  }
  a { color: var(--blue); }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 0 24px; }

  /* --- Nav --- */
  nav.top {
    border-bottom: 1px solid var(--border);
    background: var(--card);
  }
  nav.top .wrap {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 16px;
    padding-bottom: 16px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 17px;
    font-weight: 600;
  }
  .brand .flag-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: linear-gradient(135deg, var(--blue) 0 50%, var(--red) 50% 100%);
    flex-shrink: 0;
  }
  nav.top .links { display: flex; gap: 22px; font-size: 14px; font-weight: 500; }
  nav.top .links a { color: var(--ink-soft); text-decoration: none; }
  nav.top .links a:hover { color: var(--blue); }

  /* --- Hero --- */
  .hero {
    padding: 64px 0 56px;
    display: grid;
    grid-template-columns: 1.1fr 1fr;
    gap: 48px;
    align-items: start;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 13px;
    font-weight: 500;
    color: var(--ink-soft);
    background: var(--card);
    border: 1px solid var(--border);
    padding: 6px 12px;
    border-radius: 100px;
    margin-bottom: 20px;
  }
  .status-pill .dot { width: 8px; height: 8px; border-radius: 50%; background: #9aa3b2; }
  .status-pill .dot.ok { background: #1f9d55; }
  .status-pill .dot.bad { background: var(--red); }
  .hero h1 {
    font-size: 42px;
    line-height: 1.12;
    margin: 0 0 18px;
    max-width: 15ch;
  }
  .hero p.lead {
    font-size: 17px;
    color: var(--ink-soft);
    max-width: 46ch;
    margin: 0 0 28px;
  }
  .hero .ctas { display: flex; gap: 12px; flex-wrap: wrap; }
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 11px 18px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    text-decoration: none;
    border: 1px solid transparent;
  }
  .btn.primary { background: var(--blue); color: #fff; }
  .btn.primary:hover { background: var(--blue-dark); }
  .btn.secondary { background: var(--card); color: var(--ink); border-color: var(--border); }
  .btn.secondary:hover { border-color: var(--blue); color: var(--blue); }

  /* --- Calculator card --- */
  .calc-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
  }
  .calc-card h2 { font-size: 15px; margin: 0 0 4px; }
  .calc-card .sub { font-size: 13px; color: var(--ink-soft); margin: 0 0 20px; }
  .field { margin-bottom: 14px; }
  .field label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--ink-soft);
    margin-bottom: 6px;
  }
  .field input, .field select {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 7px;
    font-size: 14px;
    font-family: inherit;
    background: #fbfbfd;
    color: var(--ink);
  }
  .field input:focus, .field select:focus {
    outline: 2px solid var(--gold);
    outline-offset: 1px;
    border-color: var(--blue);
  }
  .calc-card button {
    width: 100%;
    padding: 11px;
    border-radius: 8px;
    border: none;
    background: var(--blue);
    color: #fff;
    font-size: 14px;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    margin-top: 4px;
  }
  .calc-card button:hover { background: var(--blue-dark); }
  .calc-card button:disabled { background: #aab3c5; cursor: wait; }
  #resultados { margin-top: 18px; }
  .opcao {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 10px 0;
    border-top: 1px solid var(--border);
    font-size: 13px;
  }
  .opcao .nome { font-weight: 500; }
  .opcao .cat { color: var(--ink-soft); font-size: 12px; display: block; }
  .opcao .preco { font-weight: 700; font-family: 'Space Grotesk', sans-serif; white-space: nowrap; }
  .aviso-erro {
    font-size: 13px;
    color: var(--red);
    background: #fdecee;
    border: 1px solid #f6c3ca;
    border-radius: 7px;
    padding: 10px 12px;
    margin-top: 14px;
  }

  /* --- Sections --- */
  section { padding: 40px 0; border-top: 1px solid var(--border); }
  section h2 { font-size: 24px; margin: 0 0 8px; }
  section p.section-lead { color: var(--ink-soft); font-size: 15px; max-width: 60ch; margin: 0 0 28px; }

  .servicos-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
  }
  .servico-card {
    border: 1px solid var(--border);
    background: var(--card);
    border-radius: 10px;
    padding: 18px;
  }
  .servico-card .peso-max {
    display: inline-block;
    font-size: 12px;
    font-weight: 600;
    color: var(--blue);
    background: #eaeffb;
    padding: 3px 9px;
    border-radius: 100px;
    margin-bottom: 10px;
  }
  .servico-card h3 { font-size: 15px; margin: 0 0 6px; }
  .servico-card p { font-size: 13px; color: var(--ink-soft); margin: 0; }

  .tabs { display: flex; gap: 4px; margin-bottom: 0; border-bottom: 1px solid var(--border); }
  .tab-btn {
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 600;
    font-family: inherit;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--ink-soft);
    cursor: pointer;
  }
  .tab-btn.active { color: var(--blue); border-bottom-color: var(--blue); }
  pre.code-block {
    background: #0e1b33;
    color: #e7ebf5;
    padding: 20px;
    border-radius: 0 0 10px 10px;
    overflow-x: auto;
    font-size: 13px;
    line-height: 1.6;
    margin: 0;
  }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  .principios { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; }
  .principio h3 { font-size: 15px; margin: 0 0 6px; display: flex; align-items: center; gap: 8px; }
  .principio h3 .marca { color: var(--red); }
  .principio p { font-size: 13px; color: var(--ink-soft); margin: 0; }

  footer { padding: 32px 0 48px; }
  footer p { font-size: 13px; color: var(--ink-soft); margin: 0; }
  footer a { color: var(--ink-soft); text-decoration: underline; }

  @media (max-width: 820px) {
    .hero { grid-template-columns: 1fr; }
    .hero h1 { font-size: 32px; }
  }
</style>
</head>
<body>

<nav class="top">
  <div class="wrap">
    <div class="brand"><span class="flag-dot"></span> API de Frete CCV</div>
    <div class="links">
      <a href="/docs">Documentação</a>
      <a href="/redoc">ReDoc</a>
      <a href="/health">Estado</a>
    </div>
  </div>
</nav>

<div class="wrap">
  <section class="hero" style="border-top:none;">
    <div>
      <div class="status-pill" id="status-pill"><span class="dot" id="status-dot"></span><span id="status-texto">A verificar estado do serviço…</span></div>
      <h1>Calcula o frete dos Correios de Cabo Verde direto no teu checkout.</h1>
      <p class="lead">Tarifário oficial dos CCV, estruturado e servido por API — sem simuladores, sem scraping. Envia o peso e o destino, recebe todas as opções de envio ordenadas por preço.</p>
      <div class="ctas">
        <a class="btn primary" href="/docs">Ver documentação Swagger</a>
        <a class="btn secondary" href="#exemplos">Ver exemplos de código</a>
      </div>
    </div>

    <div class="calc-card">
      <h2>Experimenta agora</h2>
      <p class="sub">Chama o endpoint <code>/api/v1/calcular-frete</code> em tempo real.</p>
      <form id="calc-form">
        <div class="field">
          <label for="peso_g">Peso (gramas)</label>
          <input type="number" id="peso_g" name="peso_g" value="1200" min="1" max="20000" required>
        </div>
        <div class="field">
          <label for="destino">Destino</label>
          <select id="destino" name="destino">
            <option value="nacional">Nacional</option>
            <option value="internacional">Internacional</option>
          </select>
        </div>
        <button type="submit" id="calc-btn">Calcular frete</button>
      </form>
      <div id="resultados"></div>
    </div>
  </section>

  <section id="servicos">
    <h2>Serviços cobertos</h2>
    <p class="section-lead">O tarifário nacional dos CCV é único para todo o arquipélago — não há diferenciação por ilha de origem ou destino, só por peso e serviço.</p>
    <div class="servicos-grid">
      <div class="servico-card">
        <span class="peso-max">até 5.000 g</span>
        <h3>Encomendas E-commerce</h3>
        <p>Tarifa dedicada a encomendas de lojas online.</p>
      </div>
      <div class="servico-card">
        <span class="peso-max">até 20.000 g</span>
        <h3>Encomendas Postais</h3>
        <p>Balcão, domicílio, ou recolha e entrega ao domicílio.</p>
      </div>
      <div class="servico-card">
        <span class="peso-max">sem limite</span>
        <h3>Correio Expresso (EMS)</h3>
        <p>Envio prioritário, com fração adicional acima de 1.000 g.</p>
      </div>
      <div class="servico-card">
        <span class="peso-max">até 2.000 g</span>
        <h3>Correio Normal / Azul</h3>
        <p>Correspondência, impressos e jornais.</p>
      </div>
    </div>
  </section>

  <section id="exemplos">
    <h2>Exemplos de consumo</h2>
    <p class="section-lead">O mesmo pedido, em quatro linguagens diferentes.</p>
    <div class="tabs">
      <button class="tab-btn active" data-tab="curl">cURL</button>
      <button class="tab-btn" data-tab="js">JavaScript</button>
      <button class="tab-btn" data-tab="python">Python</button>
      <button class="tab-btn" data-tab="php">PHP</button>
    </div>
    <div class="tab-panel active" data-panel="curl"><pre class="code-block">curl -X POST 'https://SEU-DOMINIO/api/v1/calcular-frete' \\
  -H 'Content-Type: application/json' \\
  -d '{"peso_g": 1200, "destino": "nacional"}'</pre></div>
    <div class="tab-panel" data-panel="js"><pre class="code-block">const resposta = await fetch('https://SEU-DOMINIO/api/v1/calcular-frete', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ peso_g: 1200, destino: 'nacional' }),
});
const dados = await resposta.json();
console.log(dados.opcoes); // opções ordenadas da mais barata para a mais cara</pre></div>
    <div class="tab-panel" data-panel="python"><pre class="code-block">import requests

resposta = requests.post(
    "https://SEU-DOMINIO/api/v1/calcular-frete",
    json={"peso_g": 1200, "destino": "nacional"},
)
dados = resposta.json()
print(dados["opcoes"])</pre></div>
    <div class="tab-panel" data-panel="php"><pre class="code-block">$ch = curl_init('https://SEU-DOMINIO/api/v1/calcular-frete');
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
    CURLOPT_POSTFIELDS => json_encode(['peso_g' => 1200, 'destino' => 'nacional']),
]);
$dados = json_decode(curl_exec($ch), true);
print_r($dados['opcoes']);</pre></div>
  </section>

  <section>
    <h2>Porque confiar nos dados</h2>
    <p class="section-lead">Pensado para um contexto institucional, não só para um protótipo.</p>
    <div class="principios">
      <div class="principio">
        <h3><span class="marca">•</span> Fonte oficial, sem scraping</h3>
        <p>O tarifário vem do PDF publicado pelos CCV, extraído e estruturado — nunca de raspagem do simulador web deles.</p>
      </div>
      <div class="principio">
        <h3><span class="marca">•</span> Validação antes de aplicar</h3>
        <p>Qualquer atualização do tarifário é validada (preços positivos, escalões coerentes) antes de entrar em produção.</p>
      </div>
      <div class="principio">
        <h3><span class="marca">•</span> Variações suspeitas ficam em espera</h3>
        <p>Alterações de preço acima de 20% face ao tarifário atual são sinalizadas e exigem confirmação explícita.</p>
      </div>
      <div class="principio">
        <h3><span class="marca">•</span> Auditoria de cada alteração</h3>
        <p>Todas as atualizações do tarifário ficam registadas, com o antes, o depois e a origem.</p>
      </div>
    </div>
  </section>

  <footer>
    <p>Dados baseados no tarifário oficial dos <a href="https://correios.cv/os-ccv/governanca-coorporativa/precario" target="_blank" rel="noopener">Correios de Cabo Verde, S.A.</a> — este serviço não é operado pelos CCV.</p>
  </footer>
</div>

<script>
// --- Estado do serviço (pill no topo) ---
fetch('/health').then(r => r.json()).then(d => {
  const dot = document.getElementById('status-dot');
  const texto = document.getElementById('status-texto');
  if (d.status === 'ok') {
    dot.classList.add('ok');
    texto.textContent = 'Serviço operacional · v' + d.versao;
  } else {
    dot.classList.add('bad');
    texto.textContent = 'Serviço degradado';
  }
}).catch(() => {
  document.getElementById('status-dot').classList.add('bad');
  document.getElementById('status-texto').textContent = 'Não foi possível verificar o estado';
});

// --- Calculadora ---
const form = document.getElementById('calc-form');
const resultadosEl = document.getElementById('resultados');
const btn = document.getElementById('calc-btn');

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  btn.disabled = true;
  btn.textContent = 'A calcular…';
  resultadosEl.innerHTML = '';

  const peso_g = parseInt(document.getElementById('peso_g').value, 10);
  const destino = document.getElementById('destino').value;

  try {
    const resposta = await fetch('/api/v1/calcular-frete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ peso_g, destino }),
    });
    const dados = await resposta.json();

    if (!resposta.ok) {
      resultadosEl.innerHTML = '<div class="aviso-erro">' + (dados.detail || 'Não foi possível calcular o frete.') + '</div>';
    } else {
      resultadosEl.innerHTML = dados.opcoes.map(o => `
        <div class="opcao">
          <div>
            <span class="nome">${o.servico}</span>
            <span class="cat">${o.categoria} · ${o.faixa_peso_g}</span>
          </div>
          <div class="preco">${o.preco.toLocaleString('pt-PT')} ${o.moeda}</div>
        </div>
      `).join('');
    }
  } catch (e) {
    resultadosEl.innerHTML = '<div class="aviso-erro">Erro de rede ao contactar a API.</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Calcular frete';
  }
});

// --- Tabs de exemplos de código ---
document.querySelectorAll('.tab-btn').forEach(botao => {
  botao.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    botao.classList.add('active');
    document.querySelector(`.tab-panel[data-panel="${botao.dataset.tab}"]`).classList.add('active');
  });
});
</script>

</body>
</html>
"""
