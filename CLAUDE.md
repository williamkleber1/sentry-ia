# CLAUDE.md

Esse arquivo é lido automaticamente pelo Claude Code quando ele entra no projeto.
Contém o contexto que ele precisa pra trabalhar aqui sem você ter que explicar tudo de novo a cada sessão.

---

## Sobre este projeto

POC para a palestra **"Do alerta ao card: bug fixing proativo com Sentry e IA"** que o
William Alves vai apresentar na **Comunidade IA da Hitss em 16/06/2026**.

A apresentação tem 21 slides (em outro repo) e essa POC é a demonstração ao vivo de uns
4-5 minutos no final. O objetivo é mostrar como Sentry + LLM podem transformar bug
fixing reativo em proativo: erro acontece, IA analisa com contexto rico, card aparece
no board já diagnosticado.

**O autor é dev backend na Hitss** (Global Hitss), trabalha com WhatsApp Business broker
integrado ao Genesys Cloud. Stack do dia a dia: Python/FastAPI, AWS serverless (Lambda,
SQS, EventBridge), Kubernetes, ArgoCD/Helm. Tech lead: Rafael Cruvinel.

## Status atual

✅ Estrutura do projeto montada
✅ Endpoints implementados (`/trigger-error`, `/sentry-webhook`, `/test-analyze`, `/healthz`)
✅ Cliente LLM com abstração Claude/OpenAI
✅ Cliente GitHub Issues
✅ Prompt estruturado (versão inicial — provavelmente precisa iterar)
✅ Roteiro de demo escrito
⏳ William ainda precisa: rodar `test_local.py` pela primeira vez, configurar Sentry
   webhook, gravar vídeo backup, ensaiar a demo

## Decisões de arquitetura importantes

### 1. Background task no webhook do Sentry
O Sentry tem **timeout de 1 segundo** no webhook. Se demorar mais, ele desconecta a
integration depois de 1000 timeouts. Como LLM leva 5-10s pra responder, o endpoint
`/sentry-webhook` em `app/main.py` retorna `200 OK` imediatamente usando
`BackgroundTasks` do FastAPI e processa o LLM + GitHub em background.

**Não mude isso pra síncrono** — vai quebrar a demo.

### 2. Abstração de provider LLM
`app/llm.py` aceita `LLM_PROVIDER=claude|openai` via env. Claude é o default. O contrato
é: dado um payload do Sentry, retornar um `dict` com keys conhecidas (`title`, `severity`,
`root_cause`, `suggested_fix`, `affected_areas`, `estimated_effort`, `labels`, `confidence`).

### 3. GitHub Issues, não Jira
Por simplicidade da demo. Jira na Hitss tem SSO/Okta que complica auth na hora.
Pra produção, trocar `app/github_client.py` por um Jira client (mesma interface).

### 4. Prompt estruturado é o coração da POC
`app/prompts.py` é o arquivo mais importante. Quando o William quiser melhorar a
qualidade da análise, é nesse arquivo que ele mexe — não no `llm.py`. Toda a engenharia
de extração de contexto (stack trace, breadcrumbs, request, tags) está em
`build_user_prompt()`.

## Estrutura do projeto

```
sentry-ai-poc/
├── CLAUDE.md              # este arquivo
├── README.md              # docs de usuário final (setup, run)
├── requirements.txt
├── .env.example
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── config.py          # leitura do .env
│   ├── prompts.py         # ⭐ system prompt + builder de user prompt
│   ├── llm.py             # abstração Claude/OpenAI
│   ├── github_client.py   # criação de issue formatada
│   └── main.py            # FastAPI: endpoints + Sentry SDK init
├── scripts/
│   ├── test_payload.json  # mock de erro (cenário WhatsApp Broker)
│   └── test_local.py      # roda fluxo completo SEM Sentry (dev rápido)
└── docs/
    ├── ARCHITECTURE.md    # arquitetura detalhada
    ├── PROMPT_ENGINEERING.md  # como o prompt funciona / como iterar
    ├── COMMON_TASKS.md    # tarefas frequentes (adicionar erro, iterar prompt, etc)
    ├── DEMO_DAY.md        # checklist do dia da apresentação
    └── ROTEIRO_DEMO.md    # roteiro minuto-a-minuto da demo
```

## Convenções do código

- **Python 3.11+** (usa `dict[str, Any]` em vez de `Dict`)
- **FastAPI + Pydantic v2**
- **Imports absolutos** (`from app import ...`), nunca relativos
- **`logger = logging.getLogger(__name__)`** em cada módulo
- **Type hints sempre** em funções públicas
- **Docstrings curtas** (uma linha geralmente basta, em pt-BR informal — combina com o estilo do William)
- **Tratamento defensivo de payload do Sentry**: o JSON varia por SDK/versão, então o
  parser em `build_user_prompt()` usa `.get()` com defaults em vez de `[]`/`[key]`
  direto. Mantenha esse padrão se for adicionar parsing novo.

## Comandos comuns

```bash
# Subir o servidor (durante dev)
uvicorn app.main:app --reload --port 8000

# Testar fluxo completo SEM precisar do Sentry configurado
python scripts/test_local.py

# Disparar erro proposital com Sentry rodando
curl http://localhost:8000/trigger-error?kind=null_ref
curl http://localhost:8000/trigger-error?kind=division
curl http://localhost:8000/trigger-error?kind=type
curl http://localhost:8000/trigger-error?kind=timeout

# Testar webhook sem o Sentry (simula o que ele mandaria)
curl -X POST http://localhost:8000/test-analyze \
  -H "Content-Type: application/json" \
  -d @scripts/test_payload.json

# Expor pro Sentry chegar (recomendado: Cloudflare Tunnel, URL fixa free)
cloudflared tunnel --url http://localhost:8000
```

## Pontos de atenção pro Claude Code

1. **Se eu pedir pra "melhorar o prompt"**: edite `app/prompts.py`, não `llm.py`. O prompt
   é a parte de maior alavancagem da POC.

2. **Se eu pedir pra "adicionar um novo tipo de erro" pra demo**: vá em `app/main.py`,
   função `trigger_error()`, adicione um novo `if kind == "..."`. Inclua breadcrumbs e
   tags pra dar contexto rico pro LLM.

3. **Se eu pedir pra "trocar pra Jira"**: crie `app/jira_client.py` com a mesma interface
   pública do `github_client.py` (`create_issue(analysis, event) -> {number, url}`).
   Substitua o import em `main.py`. Use o package `jira`.

4. **Se eu pedir pra rodar testes**: ainda não tem suite de teste. Se for adicionar,
   use `pytest` (já é o padrão da Hitss), com fixtures em `tests/conftest.py`.

5. **Se eu pedir mudanças nos slides**: os slides estão em **outro repo/pasta** (não aqui).
   Os arquivos `.pptx`/`.pdf` da apresentação estão em `/mnt/user-data/outputs/` ou na
   máquina do William. Não tente editar slides daqui.

6. **NÃO comite o `.env`** — só o `.env.example`. O `.gitignore` já cobre isso.

7. **Linguagem do projeto**: comentários e docstrings em pt-BR informal. O autor escreve
   assim: "tá", "pra", "daora", "show". Acompanhe esse tom.

8. **NÃO tente impressionar com over-engineering**. É uma POC de demo. Se eu pedir
   "adiciona retry exponencial", "implementa circuit breaker", "põe queue persistente" —
   pergunte se vale a pena pra demo antes de implementar. Provavelmente não vale.

## O que está fora do escopo da POC

- Autenticação no endpoint webhook (em prod usaria HMAC do Sentry; pra demo é open)
- Persistência (sem DB, sem queue real — `BackgroundTasks` é só in-memory)
- Observability do próprio serviço (sem métricas, sem traces)
- Multi-tenant
- Rate limit
- Suporte a múltiplos boards simultaneamente

Se eu pedir uma dessas e for relevante pra produção, ok — mas confirme primeiro se é
pra POC ou pra evoluir pra produção real.

## Contexto da palestra (pra você entender o "por que")

A tese da palestra é: **Sentry sozinho gera dado bruto. Dev tem que parar pra triar,
investigar, abrir card, escrever contexto. Esse trabalho de tradução é onde a IA
entra**. O slide-pivô da apresentação compara:

| Sentry sozinho | Sentry + IA |
|---|---|
| Stack trace bruto | Erro chega já diagnosticado |
| Triagem manual | Severidade automática |
| Você abre o dashboard | Card aparece no board |
| Dev investiga do zero | Causa raiz sugerida vem junto |

A demo é a prova viva disso: você dispara erro, em ~10s aparece issue no GitHub com
diagnóstico, causa raiz provável, sugestão de fix, severidade, esforço estimado.

Frase-âncora da palestra que ajuda a calibrar decisões:
> "A gente automatizou tudo, menos a interpretação."
