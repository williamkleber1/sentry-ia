# Tarefas Comuns

Receitas pras coisas que você (ou o Claude Code) vai querer fazer com mais frequência
nesse projeto.

## Iterar no prompt da IA

**Arquivo:** `app/prompts.py`

```bash
# 1. Edita o SYSTEM_PROMPT ou USER_PROMPT_TEMPLATE
# 2. Roda o teste local sem precisar do Sentry
python scripts/test_local.py
# 3. Veja o JSON gerado, ajusta, repete
```

Não precisa reiniciar uvicorn nem nada. Cada run é independente.

**Dica:** copie `scripts/test_payload.json` em variantes (`test_payload_timeout.json`,
`test_payload_division.json`) e modifique `test_local.py` pra rodar em loop com todos.
Te ajuda a evitar "overfitting" no único caso de teste.

Mais detalhes em `docs/PROMPT_ENGINEERING.md`.

## Adicionar um novo tipo de erro pra demo

**Arquivo:** `app/main.py`, função `trigger_error()`.

Hoje tem 4 tipos: `null_ref`, `division`, `type`, `timeout`. Pra adicionar um quinto:

```python
if kind == "novo_kind":
    sentry_sdk.add_breadcrumb(category="business", message="Setup do contexto", level="info")
    sentry_sdk.add_breadcrumb(category="cache", message="Cache populated", level="info")
    # ... mais breadcrumbs pra dar contexto pro LLM
    sentry_sdk.set_tag("error_kind", "novo_kind")
    # ... aqui o erro de fato:
    raise ValueError("mensagem realista")
```

**Importante:** os breadcrumbs e tags são o que torna o erro "interessante" pro LLM
analisar. Um erro sem contexto vai gerar análise rasa. Pense num cenário real do
stack da Hitss (WhatsApp Broker, Genesys, etc) e simule a sequência de ações que
levou ao bug.

## Trocar GitHub Issues por Jira

**Arquivos:** novo `app/jira_client.py`, edita `app/main.py`.

1. `pip install jira` e adiciona no `requirements.txt`
2. Cria `app/jira_client.py` com **a mesma interface** do `github_client.py`:

```python
def create_issue(analysis: dict, event: dict) -> dict:
    """Retorna {'number': str, 'url': str}."""
    # ... usa o package 'jira' aqui
```

3. Adiciona envs no `.env.example`:
```
JIRA_URL=https://hitss.atlassian.net
JIRA_USER=william.alves@globalhitss.com.br
JIRA_TOKEN=...
JIRA_PROJECT=DEMO
```

4. No `app/main.py`, troca o import:
```python
# from app import github_client
from app import jira_client as issue_client
```

E substitui `github_client.create_issue(...)` por `issue_client.create_issue(...)`.

> **Cuidado:** Jira na Hitss geralmente tem SSO/Okta. Se o token de API direto não
> funcionar, pode precisar de OAuth — bem mais complicado pra demo. Por isso a POC
> começou com GitHub.

## Trocar Claude por OpenAI (ou vice-versa)

Já tem abstração. Só muda no `.env`:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

E reinicia o servidor. Sem mexer no código.

## Adicionar notificação Slack após criar issue

**Arquivo:** novo `app/slack_client.py`, edita `app/main.py`.

1. Cria webhook no Slack: https://api.slack.com/messaging/webhooks
2. Adiciona env: `SLACK_WEBHOOK_URL=https://hooks.slack.com/...`
3. Cria `app/slack_client.py`:

```python
import httpx
from app import config

def notify(analysis: dict, issue: dict) -> None:
    if not config.SLACK_WEBHOOK_URL:
        return  # opcional, não falha
    payload = {
        "text": f"🤖 Novo card gerado pela IA: <{issue['url']}|#{issue['number']}>",
        "blocks": [...]  # formatação rica
    }
    httpx.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=5)
```

4. No `_process_webhook` em `main.py`, depois de criar issue:
```python
try:
    slack_client.notify(analysis, issue)
except Exception:
    logger.exception("Slack notification failed (ignorado)")
```

> Slack é "best effort" — falha não deve quebrar o fluxo principal.

## Buscar trecho de código fonte pra enriquecer a análise

**Onde:** `app/prompts.py`, em `build_user_prompt()`.

Pra cada frame do stack, buscar ~20 linhas do código no GitHub via API:

```python
def _fetch_source_context(filename: str, lineno: int, lines: int = 20) -> str:
    """Busca linhas de contexto em torno de lineno via GitHub API."""
    # repo = config.GITHUB_REPO
    # path = filename (precisa mapear /app/services/x.py pro path real do repo)
    # GET /repos/{owner}/{repo}/contents/{path}
    # decoda base64, extrai range [lineno-10, lineno+10]
    ...
```

Adiciona no template:
```
## CÓDIGO FONTE (contexto)
```
{source_context}
```
```

**Custo:** ~1-2s adicionais de latência (chamada GitHub API). Aumenta MUITO a
qualidade do `suggested_fix`. Considere fazer se o tempo permitir antes do dia 16.

## Rodar o projeto sem internet

Pra dev/iteração rápida sem depender de Sentry Cloud ou GitHub:

```bash
# Use o endpoint /test-analyze que aceita payload mock
curl -X POST http://localhost:8000/test-analyze \
  -H "Content-Type: application/json" \
  -d @scripts/test_payload.json
```

Esse endpoint roda SÍNCRONO (não tem timeout do Sentry) e retorna a análise + url
do issue criado no response.

Se quiser não criar issue real no GitHub, pode comentar a linha `issue =
github_client.create_issue(...)` em `test_analyze` ou usar variável de env mockada.

## Debugar timeout no webhook

Se o Sentry está desconectando o webhook ("integration disabled"):

1. **Veja se está respondendo em <1s.** No log do uvicorn deve aparecer:
   ```
   INFO 200 POST /sentry-webhook ... (0.05s)
   ```
   Se aparece tempo >1s, tem coisa síncrona acontecendo no handler — deveria estar
   tudo em background.

2. **Confira `BackgroundTasks`.** O handler precisa retornar antes de qualquer chamada
   pesada. Estrutura correta:
   ```python
   @app.post("/sentry-webhook")
   async def sentry_webhook(request: Request, bg: BackgroundTasks):
       payload = await request.json()
       bg.add_task(_process_webhook, payload)  # ← agenda, não executa
       return {"status": "accepted"}  # ← retorna ANTES de processar
   ```

3. **Reative a integration** no Sentry: Settings → Developer Settings → seu app →
   tem botão pra reativar.

## Gerar payloads de teste mais realistas

`scripts/test_payload.json` é um mock simples. Pra gerar payloads reais:

1. Dispara um erro no Sentry real (`curl /trigger-error?kind=...`)
2. No dashboard do Sentry: Issues → clica no issue → JSON
3. Salva como `scripts/test_payload_<cenario>.json`

Aí dá pra testar o prompt com payloads que vieram do Sentry de verdade — mais
fidedignos.

## Limpar issues geradas durante teste

Se o repo de demo virou bagunça com issues de teste:

```bash
# Lista issues abertas com label sentry-ai
gh issue list --label sentry-ai --repo $GITHUB_REPO

# Fecha todas (ou usa --state closed pra ver as já fechadas)
gh issue list --label sentry-ai --repo $GITHUB_REPO --json number -q '.[].number' | \
  xargs -I {} gh issue close {} --repo $GITHUB_REPO
```

Requer `gh` CLI autenticado.
