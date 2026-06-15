# Sentry + IA — POC Comunidade IA Hitss

POC pra palestra "Do alerta ao card: bug fixing proativo com Sentry e IA"
(William Alves · Comunidade IA Hitss · 16/06/2026)

## O que isso faz

1. **App FastAPI** instrumentado com Sentry
2. **Endpoint `/trigger-error`** que dispara erros propositais (vários tipos)
3. **Webhook `/sentry-webhook`** que:
   - Recebe o evento do Sentry quando o erro acontece
   - Enriquece o contexto e chama o LLM (Claude/OpenAI) com prompt estruturado
   - Cria uma issue no GitHub com diagnóstico, causa raiz sugerida e fix

## Setup (uma vez)

### 1. Clonar e instalar

```bash
git clone <repo>
cd sentry-ai-poc
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Criar conta Sentry e pegar DSN

**Funciona 100% no plano Developer (free):**
- 5.000 errors/mês (sobra muito pra demo + testes)
- 1 usuário (você)
- 30 dias de retenção
- Internal Integrations + Webhooks incluídos
- Stack traces, breadcrumbs, alerts — tudo

Passos:
- Acessar https://sentry.io/signup
- Criar projeto Python → FastAPI
- Settings → Client Keys → copiar DSN

> ⚠️ **Atenção ao timeout de 1s:** o Sentry desconecta webhooks que demoram >1s
> pra responder. Como Claude/OpenAI levam 5-10s, o endpoint `/sentry-webhook`
> responde 200 imediatamente e processa em background. Isso já está implementado
> em `app/main.py`.

### 3. Criar PAT do GitHub

- https://github.com/settings/tokens (Tokens classic)
- Escopo: `repo` (Full control)
- Copiar o token

### 4. Criar repo de demo

- Criar repo público vazio no GitHub (ex: `william-alves/sentry-ai-demo`)
- Esse repo vai receber as issues geradas pela IA

### 5. Pegar API key do Claude (ou OpenAI)

- Claude: https://console.anthropic.com/ → API Keys
- (Alternativa) OpenAI: https://platform.openai.com/api-keys

### 6. Configurar `.env`

```bash
cp .env.example .env
# Editar .env e preencher SENTRY_DSN, ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_REPO
```

## Rodar localmente

### Teste rápido sem Sentry (recomendado primeiro)

Pra verificar que LLM + GitHub estão funcionando antes de mexer no Sentry:

```bash
python scripts/test_local.py
```

Esse script usa um payload mock de erro (cenário WhatsApp Broker), chama o LLM
e cria uma issue real no seu repo de demo. Roda em ~10 segundos.

### Subir o servidor FastAPI

```bash
uvicorn app.main:app --reload --port 8000
```

Em outro terminal, dispara um erro:

```bash
curl http://localhost:8000/trigger-error?kind=null_ref
```

Você verá o erro 500 (esperado) e ele será capturado pelo Sentry. Mas o
webhook ainda não vai chegar — você precisa expor a porta 8000 pra internet.

### Expor pro Sentry chegar (escolhe uma opção)

**Opção A — Cloudflare Tunnel (recomendado pra demo: URL fixa, free)**

```bash
# instalar: brew install cloudflared (Mac) ou baixar de https://github.com/cloudflare/cloudflared/releases
cloudflared tunnel --url http://localhost:8000
```

Copia a URL `https://xxxx.trycloudflare.com` que aparece. Vantagem: não muda
toda vez que reiniciar.

**Opção B — ngrok (mais conhecido)**

```bash
# instalar: brew install ngrok (Mac) ou snap install ngrok (Linux)
ngrok http 8000
```

> ⚠️ No plano free do ngrok, a URL muda toda vez que você reinicia o serviço.
> Pra demo ao vivo isso é chato — prefira Cloudflare Tunnel.

### Configurar webhook no Sentry

- Sentry → Settings → Developer Settings → New Internal Integration
- Nome: "AI Bug Analyzer"
- Webhook URL: `https://xxxx.ngrok-free.app/sentry-webhook`
- Alerts: marcar "Issue Alerts"
- Permissions: Issue & Event = Read
- Salvar

- Sentry → Alerts → Create Alert → Issue Alert
  - Quando: "A new issue is created"
  - Ação: "Send notification via AI Bug Analyzer"
  - Salvar

## Fluxo end-to-end

```
curl /trigger-error
   ↓
FastAPI levanta exception
   ↓
Sentry SDK captura, envia pro Sentry Cloud
   ↓
Sentry detecta NOVO issue, dispara webhook
   ↓
ngrok → /sentry-webhook
   ↓
analyzer chama Claude com prompt estruturado
   ↓
github_client cria issue no repo
   ↓
✨ Issue aparece no GitHub com diagnóstico + sugestão de fix
```

## Estrutura do código

```
app/
├── main.py            # FastAPI app + endpoints
├── config.py          # Configs do .env
├── prompts.py         # ⭐ Engenharia de prompt — a alma da POC
├── llm.py             # Abstração Claude/OpenAI
└── github_client.py   # Cria issue formatada

scripts/
├── test_payload.json  # Payload mock pra testar sem Sentry
└── test_local.py      # Roda o fluxo completo localmente

docs/
└── ROTEIRO_DEMO.md    # Roteiro detalhado do que mostrar na palestra
```

## Troubleshooting

**LLM retornou JSON inválido** → checar o `SYSTEM_PROMPT` em `prompts.py`,
às vezes o modelo teima em colocar texto antes. O `_extract_json` já lida
com cercas de código, mas pode precisar de ajuste.

**Sentry não dispara webhook** → criar AlertRule "Quando new issue is created"
e atrelar à Integration que você criou. Webhook só dispara em new issues
por padrão, não em ocorrências repetidas.

**ngrok URL muda toda vez** → use `ngrok config add-authtoken <token>` pra
ter URL fixa (free tier) ou pague pelo plano Pro.

**GitHub diz "label not found"** → o cliente faz fallback automático sem
labels. Crie as labels `sentry-ai`, `severity:p0..p3` no seu repo se quiser
filtragem.

## Customização

- **Trocar pra OpenAI:** mudar `LLM_PROVIDER=openai` no `.env`
- **Trocar pra Jira:** substituir `github_client.py` por client do Jira
  (API similar, basta usar `jira` package em vez de `PyGithub`)
- **Mudar o prompt:** editar `app/prompts.py` — esse é o ponto de maior alavancagem
