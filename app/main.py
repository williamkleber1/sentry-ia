"""FastAPI app — painel de demo + endpoints:

- /                  painel web com botões pra disparar erros (select de provider, checkbox Copilot)
- /scenarios         lista os cenários de erro (kind, descrição)
- /demo/run          SÍNCRONO: dispara erro -> Sentry + análise + card, devolve a prévia
- /demo/pr-status    status do PR do Copilot (polling)
- /trigger-error     dispara erro proposital pro Sentry (fluxo real via webhook)
- /sentry-webhook    recebe webhook do Sentry, processa em background (<1s)
- /test-analyze      fluxo síncrono a partir de um payload mock
- /healthz           health check
"""
import logging
import time

import sentry_sdk
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app import config, llm, issues, github_client, scenarios

# ============================================
# Sentry init
# ============================================
sentry_sdk.init(
    dsn=config.SENTRY_DSN,
    environment=config.SENTRY_ENVIRONMENT,
    traces_sample_rate=1.0,
    send_default_pii=True,
    integrations=[FastApiIntegration()],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("app")

app = FastAPI(title="Sentry + IA — POC Comunidade IA Hitss")

# Estado em memória do PR do Copilot por issue (só pra demo)
PR_STATUS: dict[int, dict] = {}


# ============================================
# Health check
# ============================================
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ============================================
# Helpers de cenário
# ============================================
def _seed_sentry(kind: str) -> None:
    """Coloca tags + breadcrumbs do cenário no escopo do Sentry."""
    sc = scenarios.get(kind)
    if not sc:
        return
    sentry_sdk.set_tag("error_kind", kind)
    sentry_sdk.set_user({"id": "demo-user-001", "username": "demo.tester"})
    for t in sc["event"]["tags"]:
        if len(t) >= 2:
            sentry_sdk.set_tag(t[0], t[1])
    for c in sc["event"]["breadcrumbs"]["values"]:
        sentry_sdk.add_breadcrumb(category=c.get("category"), message=c.get("message"),
                                  level=c.get("level", "info"))


def _poll_pr_and_link(issue_number: int) -> None:
    """Espera o Copilot abrir o PR e escreve o link na issue. Roda em background."""
    for _ in range(30):  # ~5 min (10s cada)
        try:
            url = github_client.find_pr_for_issue(issue_number)
        except Exception:
            url = None
        if url:
            PR_STATUS[issue_number] = {"state": "ready", "url": url}
            try:
                github_client.comment_on_issue(issue_number, f"🤖 Copilot abriu o PR com a correção: {url}")
            except Exception:
                logger.exception("Falha ao comentar o link do PR na issue")
            logger.info(f"🔗 PR do Copilot ligado à issue #{issue_number}: {url}")
            return
        time.sleep(10)
    PR_STATUS[issue_number] = {"state": "timeout", "url": None}


# ============================================
# Painel de demo
# ============================================
@app.get("/scenarios")
def list_scenarios():
    """Lista os cenários de erro pro painel renderizar."""
    return [{"kind": s["kind"], "emoji": s["emoji"], "label": s["label"],
             "description": s["description"]} for s in scenarios.SCENARIOS]


@app.get("/", response_class=HTMLResponse)
def demo_panel():
    """Painel de demo com botões, select de provider e checkbox de Copilot."""
    model = config.CLAUDE_MODEL if config.LLM_PROVIDER == "claude" else config.OPENAI_MODEL
    meta = f"LLM: <b>{config.LLM_PROVIDER} / {model}</b>"
    return _PANEL_TEMPLATE.replace("__META__", meta)


class DemoRun(BaseModel):
    kind: str
    provider: str = "github"
    copilot: bool = False


@app.post("/demo/run")
def demo_run(req: DemoRun, bg: BackgroundTasks):
    """Síncrono: dispara o erro (-> Sentry), analisa com a IA, cria o card e devolve a prévia."""
    sc = scenarios.get(req.kind)
    if not sc:
        raise HTTPException(status_code=400, detail=f"kind desconhecido: {req.kind}")
    provider = req.provider.lower()
    want_copilot = req.copilot and provider == "github"

    # 1) manda o erro pro Sentry (acende o dashboard)
    _seed_sentry(req.kind)
    try:
        scenarios.raise_scenario(req.kind)
    except Exception as e:
        sentry_sdk.capture_exception(e)

    # 2) análise + card (provider/copilot escolhidos no painel)
    event = sc["event"]
    analysis = llm.analyze_event(event)
    card = issues.create_issue(analysis, event, provider=provider, assign_copilot=want_copilot)
    logger.info(f"🎫 Card criado ({provider}): {card['url']}")

    # 3) se assignou Copilot, dispara o poller do PR
    if want_copilot and card.get("copilot_assigned"):
        PR_STATUS[card["number"]] = {"state": "working", "url": None}
        bg.add_task(_poll_pr_and_link, card["number"])

    return {
        "ok": True,
        "kind": req.kind,
        "provider": provider,
        "analysis": analysis,
        "card": card,
        "copilot": {"requested": req.copilot, "assigned": card.get("copilot_assigned", False),
                    "available": provider == "github"},
    }


@app.get("/demo/pr-status")
def pr_status(number: int):
    """Status do PR do Copilot pra issue (working|ready|timeout|unknown)."""
    return PR_STATUS.get(number, {"state": "unknown", "url": None})


# ============================================
# Endpoint que SIMULA app real com erros (fluxo real via Sentry webhook)
# ============================================
@app.get("/trigger-error")
def trigger_error(kind: str = "null_ref"):
    """Dispara um erro proposital pra Sentry capturar (use ?kind=<tipo>)."""
    if not scenarios.get(kind):
        raise HTTPException(status_code=400, detail=f"kind desconhecido: {kind}")
    logger.info(f"Disparando erro proposital: {kind}")
    _seed_sentry(kind)
    scenarios.raise_scenario(kind)  # propaga -> Sentry captura -> 500


# ============================================
# Processamento em background do webhook do Sentry (responde <1s)
# ============================================
def _process_webhook(payload: dict) -> None:
    """Roda fora do request do Sentry. Chama LLM e cria issue."""
    try:
        logger.info("🤖 Análise iniciada em background...")
        analysis = llm.analyze_event(payload)
        logger.info(f"✅ Análise: severity={analysis.get('severity')}, "
                    f"effort={analysis.get('estimated_effort')}")
    except Exception:
        logger.exception("Falha na análise do LLM")
        return

    try:
        # 'data' do webhook do Sentry: alert rule manda data.event; webhook de
        # resource manda data.error (error.created) ou data.issue (issue.*)
        d = payload.get("data", {}) or {}
        event_data = d.get("event") or d.get("error") or d.get("issue") or payload.get("event") or payload
        issue = issues.create_issue(analysis, event_data)
        logger.info(f"🎫 Issue criada: {issue['url']}")
    except Exception:
        logger.exception("Falha ao criar issue")


@app.post("/sentry-webhook")
async def sentry_webhook(request: Request, bg: BackgroundTasks):
    """Recebe webhook do Sentry. Responde 200 imediatamente; processa LLM em background."""
    payload = await request.json()
    logger.info(f"📨 Webhook recebido. Resource: {request.headers.get('sentry-hook-resource')}")
    bg.add_task(_process_webhook, payload)
    return {"status": "accepted", "queued": True}


# ============================================
# Endpoint de TESTE — payload manual (sem Sentry)
# ============================================
@app.post("/test-analyze")
async def test_analyze(request: Request):
    """Recebe um payload de erro JSON (mock) e roda o fluxo completo SÍNCRONO."""
    payload = await request.json()
    analysis = llm.analyze_event(payload)
    event_data = payload.get("data", {}).get("event") or payload.get("event") or payload
    issue = issues.create_issue(analysis, event_data)
    return {"status": "ok", "analysis": analysis, "issue": issue}


# ============================================
# HTML do painel
# ============================================
_PANEL_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentry + IA — Painel de Demo</title>
<style>
  :root { --bg:#0e1116; --card:#1b2027; --card2:#10151b; --accent:#a371f7; --text:#e6edf3;
          --muted:#8b949e; --line:#2a313a; --ok:#3fb950; --p0:#f85149; --p1:#f0883e; --p2:#d29922; --p3:#58a6ff; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg);
         color:var(--text); min-height:100vh; padding:48px 24px; }
  .wrap { max-width:1040px; margin:0 auto; }
  h1 { font-size:30px; margin:0 0 4px; }
  .sub { color:var(--muted); margin:0 0 8px; font-size:15px; }
  .meta { color:var(--muted); font-size:13px; margin-bottom:24px; }
  .meta b { color:var(--accent); }
  .controls { display:flex; gap:20px; align-items:center; flex-wrap:wrap; background:var(--card2);
              border:1px solid var(--line); border-radius:12px; padding:14px 18px; margin-bottom:24px; }
  .controls label { font-size:14px; color:var(--muted); display:flex; align-items:center; gap:8px; }
  select { background:var(--card); color:var(--text); border:1px solid var(--line);
           border-radius:8px; padding:8px 10px; font-size:14px; }
  input[type=checkbox] { width:18px; height:18px; accent-color:var(--accent); }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
  @media(max-width:860px){ .cols{ grid-template-columns:1fr; } }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .trigger { text-align:left; cursor:pointer; border:1px solid var(--line); background:var(--card);
             color:var(--text); border-radius:12px; padding:16px; transition:.15s; }
  .trigger:hover { border-color:var(--accent); transform:translateY(-2px); }
  .trigger:disabled { opacity:.45; cursor:wait; transform:none; }
  .trigger .emoji { font-size:24px; }
  .trigger .t { font-weight:600; font-size:15px; margin:8px 0 4px; }
  .trigger .d { color:var(--muted); font-size:12px; line-height:1.4; }
  .panel { background:var(--card2); border:1px solid var(--line); border-radius:12px; padding:20px; min-height:340px; }
  .panel h2 { font-size:15px; margin:0 0 14px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
  .badge { display:inline-block; padding:3px 10px; border-radius:20px; font-weight:700; font-size:13px; color:#0e1116; }
  .row { margin:14px 0; }
  .row .k { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }
  .row .v { font-size:14px; line-height:1.5; }
  pre { background:#0a0d11; border:1px solid var(--line); border-radius:8px; padding:12px;
        overflow:auto; font-size:13px; white-space:pre-wrap; }
  .tag { display:inline-block; background:var(--card); border:1px solid var(--line); border-radius:6px;
         padding:2px 8px; font-size:12px; margin:2px 4px 2px 0; color:var(--muted); }
  a.cardlink { display:inline-block; margin-top:6px; color:var(--accent); text-decoration:none; font-weight:600; }
  a.cardlink:hover { text-decoration:underline; }
  .status { color:var(--muted); font-size:14px; }
  .spinner { display:inline-block; width:14px; height:14px; border:2px solid var(--line);
             border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite; vertical-align:-2px; }
  @keyframes spin { to { transform:rotate(360deg); } }
</style>
</head>
<body>
<div class="wrap">
  <h1>🛰️ Sentry + IA — Painel de Demo</h1>
  <p class="sub">Do alerta ao card: bug fixing proativo com Sentry e IA</p>
  <p class="meta">__META__</p>

  <div class="controls">
    <label>Board:
      <select id="provider" onchange="onProvider()">
        <option value="github">GitHub Issues</option>
        <option value="jira">Jira</option>
      </select>
    </label>
    <label><input type="checkbox" id="copilot"> Copilot abre o PR <span id="copnote" class="status"></span></label>
  </div>

  <div class="cols">
    <div>
      <div class="grid" id="buttons"></div>
    </div>
    <div class="panel" id="result">
      <h2>Resultado</h2>
      <p class="status">Escolha o board, (opcional) marque o Copilot e clique num cenário.</p>
    </div>
  </div>
</div>
<script>
const SEV = {P0:'--p0',P1:'--p1',P2:'--p2',P3:'--p3'};
const cssvar = n => getComputedStyle(document.documentElement).getPropertyValue(n);

async function loadScenarios(){
  const r = await fetch('/scenarios'); const list = await r.json();
  const box = document.getElementById('buttons');
  box.innerHTML = list.map(s =>
    `<button class="trigger" data-kind="${s.kind}" onclick="run('${s.kind}',this)">
       <div class="emoji">${s.emoji}</div><div class="t">${s.label}</div>
       <div class="d">${s.description}</div></button>`).join('');
}

function onProvider(){
  const isGh = document.getElementById('provider').value === 'github';
  const cb = document.getElementById('copilot');
  cb.disabled = !isGh; if(!isGh) cb.checked = false;
  document.getElementById('copnote').textContent = isGh ? '' : '(só no GitHub)';
}

function esc(s){ return (s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

async function run(kind, btn){
  const provider = document.getElementById('provider').value;
  const copilot = document.getElementById('copilot').checked;
  const res = document.getElementById('result');
  document.querySelectorAll('.trigger').forEach(b => b.disabled = true);
  res.innerHTML = `<h2>Resultado</h2><p class="status"><span class="spinner"></span> Erro disparado → Sentry → IA analisando…</p>`;
  try {
    const r = await fetch('/demo/run', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({kind, provider, copilot})});
    const d = await r.json();
    if(!d.ok){ res.innerHTML = `<h2>Resultado</h2><p class="status">Erro: ${esc(JSON.stringify(d))}</p>`; return; }
    const a = d.analysis, sev = a.severity || 'P2';
    const color = cssvar(SEV[sev] || '--muted');
    let html = `<h2>Prévia da análise (IA)</h2>`;
    html += `<div class="row"><span class="badge" style="background:${color}">${sev}</span>
             &nbsp;<b>${esc(a.title)}</b></div>`;
    html += `<div class="row"><div class="k">🔍 Causa raiz</div><div class="v">${esc(a.root_cause)}</div></div>`;
    html += `<div class="row"><div class="k">🔧 Sugestão de correção</div><pre>${esc(a.suggested_fix)}</pre></div>`;
    html += `<div class="row"><div class="k">📍 Áreas afetadas</div><div class="v">${(a.affected_areas||[]).map(x=>`<span class="tag">${esc(x)}</span>`).join('')}</div></div>`;
    html += `<div class="row"><div class="k">⏱️ Esforço / Confiança</div><div class="v">${esc(a.estimated_effort)} · ${esc(a.confidence)}</div></div>`;
    html += `<div class="row"><div class="k">🎫 Card criado (${d.provider})</div>
             <a class="cardlink" href="${d.card.url}" target="_blank">${d.card.url}</a></div>`;
    if(d.copilot.assigned){
      html += `<div class="row" id="prrow"><div class="k">🤖 Copilot</div>
               <div class="v status" id="prstatus"><span class="spinner"></span> abrindo o PR (~minutos)…</div></div>`;
    } else if(d.copilot.requested && !d.copilot.available){
      html += `<div class="row"><div class="k">🤖 Copilot</div><div class="v status">ignorado (só no GitHub)</div></div>`;
    }
    res.innerHTML = html;
    if(d.copilot.assigned) pollPR(d.card.number);
  } catch(e){
    res.innerHTML = `<h2>Resultado</h2><p class="status">Falha de rede: ${esc(String(e))}</p>`;
  } finally {
    document.querySelectorAll('.trigger').forEach(b => b.disabled = false);
  }
}

async function pollPR(number){
  for(let i=0;i<40;i++){
    await new Promise(r=>setTimeout(r,8000));
    try{
      const r = await fetch('/demo/pr-status?number='+number); const d = await r.json();
      const el = document.getElementById('prstatus'); if(!el) return;
      if(d.state==='ready'){ el.innerHTML = `✅ PR aberto: <a class="cardlink" href="${d.url}" target="_blank">${d.url}</a>`; return; }
      if(d.state==='timeout'){ el.textContent = 'PR não saiu no tempo do poll — confira no GitHub.'; return; }
    }catch(e){}
  }
}

loadScenarios(); onProvider();
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.APP_PORT, reload=True)
