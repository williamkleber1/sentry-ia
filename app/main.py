"""FastAPI app — três endpoints:

1. /trigger-error — dispara um erro proposital pro Sentry capturar
2. /sentry-webhook — recebe webhook do Sentry, processa em background (responde <1s)
3. /healthz — health check
"""
import logging
import sentry_sdk
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app import config, llm, github_client

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


# ============================================
# Health check
# ============================================
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ============================================
# Endpoint que SIMULA app real com erros
# (na demo, isso seria a aplicação que você instrumentou com Sentry)
# ============================================
@app.get("/trigger-error")
def trigger_error(kind: str = "null_ref"):
    """Dispara um erro proposital pra Sentry capturar.

    Use ?kind=<tipo> pra escolher o cenário:
      - null_ref:  AttributeError em dict sem chave (default)
      - division:  ZeroDivisionError
      - type:      TypeError em soma string + int
      - timeout:   simula timeout em chamada externa
    """
    logger.info(f"Disparando erro proposital: {kind}")

    # Adicionar breadcrumbs pra dar contexto
    sentry_sdk.add_breadcrumb(category="api", message=f"Iniciando processamento ({kind})", level="info")
    sentry_sdk.set_tag("error_kind", kind)
    sentry_sdk.set_user({"id": "demo-user-001", "username": "wagner.tester"})

    if kind == "null_ref":
        sentry_sdk.add_breadcrumb(category="db", message="Buscando cliente no DB", level="info")
        sentry_sdk.add_breadcrumb(category="cache", message="Cache miss, indo no DB", level="warning")
        cliente = {"nome": "João"}  # bug: faltou o campo "email"
        return {"email": cliente["email"].lower()}

    if kind == "division":
        sentry_sdk.add_breadcrumb(category="business", message="Calculando taxa por usuário", level="info")
        total_usuarios = 0  # bug: divisão por zero quando não há usuários
        return {"taxa": 100 / total_usuarios}

    if kind == "type":
        sentry_sdk.add_breadcrumb(category="parsing", message="Parsing payload", level="info")
        idade = "42"
        return {"idade_no_proximo_ano": idade + 1}  # bug: string + int

    if kind == "timeout":
        sentry_sdk.add_breadcrumb(category="http", message="Chamando API externa", level="info")
        raise TimeoutError("Genesys API não respondeu em 30s")

    raise HTTPException(status_code=400, detail=f"kind desconhecido: {kind}")


# ============================================
# Processamento em background — IMPORTANTE:
# Sentry webhook tem timeout de 1s, então não dá pra chamar LLM síncrono.
# Devolvemos 200 IMEDIATAMENTE e processamos depois.
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
        # 'data' do webhook do Sentry envelopa o event
        event_data = payload.get("data", {}).get("event") or payload.get("event") or payload
        issue = github_client.create_issue(analysis, event_data)
        logger.info(f"🎫 Issue criada: {issue['url']}")
    except Exception:
        logger.exception("Falha ao criar issue no GitHub")


# ============================================
# Endpoint que RECEBE o webhook do Sentry
# Responde em <1s e processa o resto em background
# ============================================
@app.post("/sentry-webhook")
async def sentry_webhook(request: Request, bg: BackgroundTasks):
    """Recebe webhook do Sentry. Responde 200 imediatamente; processa LLM em background.

    Necessário porque o Sentry tem timeout de 1s no webhook. LLM leva ~5-10s.
    """
    payload = await request.json()
    logger.info(f"📨 Webhook recebido. Resource: {request.headers.get('sentry-hook-resource')}")

    # Agenda processamento em background
    bg.add_task(_process_webhook, payload)

    # Retorna 200 IMEDIATAMENTE
    return {"status": "accepted", "queued": True}


# ============================================
# Endpoint de TESTE — recebe um payload manualmente pra testar fluxo
# (sem precisar do Sentry — útil durante o desenvolvimento)
# ============================================
@app.post("/test-analyze")
async def test_analyze(request: Request):
    """Recebe um payload de erro JSON (mock) e roda o fluxo completo SÍNCRONO.

    Use isso pra testar sem depender do Sentry estar configurado.
    """
    payload = await request.json()
    analysis = llm.analyze_event(payload)
    # Suporta tanto payload "puro" quanto envelope do webhook
    event_data = payload.get("data", {}).get("event") or payload.get("event") or payload
    issue = github_client.create_issue(analysis, event_data)
    return {"status": "ok", "analysis": analysis, "issue": issue}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.APP_PORT, reload=True)
