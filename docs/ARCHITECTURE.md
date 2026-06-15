# Arquitetura

Detalhes técnicos do fluxo. Pra entender O QUE faz cada peça e POR QUE foi assim.

## Visão de fluxo

```
┌──────────────────┐
│   App FastAPI    │  (esse mesmo projeto faz dois papéis)
│  /trigger-error  │  ─ 1. Cliente dispara erro proposital
└────────┬─────────┘
         │
         │  exception é levantada
         ▼
┌──────────────────┐
│   Sentry SDK     │  ─ 2. Captura: stack, breadcrumbs, request, tags
│   (in-process)   │
└────────┬─────────┘
         │
         │  HTTP POST ao Sentry Cloud
         ▼
┌──────────────────┐
│   Sentry Cloud   │  ─ 3. Recebe evento, agrupa em issue, dispara webhook
└────────┬─────────┘
         │
         │  HTTP POST (com timeout de 1s!)
         ▼
┌──────────────────┐
│ Cloudflare Tunnel│  ─ 4. Expõe localhost:8000 pra internet com URL fixa
│  / ngrok         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  /sentry-webhook │  ─ 5. Recebe payload, agenda BackgroundTask,
│  (mesmo app)     │       retorna 200 IMEDIATAMENTE
└────────┬─────────┘
         │
         │  bg.add_task(_process_webhook, payload)
         ▼
┌──────────────────┐
│  _process_webhook│  ─ 6. Roda fora do request:
│   (background)   │       a) chama llm.analyze_event()
│                  │       b) chama github_client.create_issue()
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   Claude / GPT   │  ─ 7. Recebe prompt estruturado, devolve JSON
│   (API externa)  │       com diagnóstico, fix, severidade
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   GitHub Issues  │  ─ 8. Issue criada com markdown formatado
│   (API externa)  │
└──────────────────┘
```

## Decisões técnicas e por quê

### Por que `BackgroundTasks` e não Celery/Arq/queue real?

POC simples. Pra demo single-process, `BackgroundTasks` do FastAPI basta — roda na
thread pool depois do response. Se cair, perde a análise daquele erro, mas Sentry
re-tenta o webhook em alguns casos.

**Pra produção**, eu trocaria pra: SQS → Lambda (que é o padrão dele na Hitss).
O payload do Sentry tem tudo que precisa, então é stateless.

### Por que API key e não OAuth no Sentry?

Internal Integrations geram um access token que não expira e tem scope na organização.
Pra POC interno é o ideal — sem OAuth dance, sem refresh token.

### Por que JSON estruturado e não markdown direto do LLM?

Dois motivos:
1. **Determinismo**: campos esperados (`severity`, `effort`, `confidence`) precisam estar
   em locais previsíveis pro `github_client.py` formatar e o usuário filtrar/agrupar
   issues. Markdown livre não dá essa garantia.
2. **Quality gate**: se o LLM falhar em produzir JSON válido, a gente sabe imediatamente
   (`LLMError`) e pode logar/alertar. Markdown livre passaria sempre.

O custo é que o prompt precisa ser mais cuidadoso (instruções claras sobre o schema).
O `_extract_json()` em `llm.py` é defensivo: tolera cercas de código residuais (`` ``` ``).

### Por que Cloudflare Tunnel e não ngrok?

ngrok free muda URL toda vez que você reinicia. Pra demo ao vivo é arriscado — você
configura webhook no Sentry com URL X, reinicia tunnel pra trocar uma config, ngrok
te dá URL Y, demo quebra.

Cloudflare Tunnel: URL fixa `*.trycloudflare.com`, free pra sempre, instalação `brew
install cloudflared`. Zero config:

```bash
cloudflared tunnel --url http://localhost:8000
```

Pra prod, ambos seriam substituídos por deploy real (Lambda Function URL, Railway,
Render, Fly.io free tier).

### Por que o webhook responde 200 mesmo se a análise falhou?

Porque o Sentry desconecta a integration depois de 1000 timeouts em 24h. Não vale a
pena fazer o Sentry esperar a confirmação de que tudo deu certo — se algo falhar no
LLM ou GitHub, isso fica nos logs locais e a gente investiga depois. Errar pro lado
de "Sentry feliz" é mais importante.

## Contratos das interfaces internas

### `llm.analyze_event(event: dict) -> dict`

**Input:** payload do Sentry webhook (qualquer envelope — `_extract_json` desempacota)

**Output:** dict com schema fixo:
```python
{
    "title": str,           # máx 80 chars
    "severity": "P0" | "P1" | "P2" | "P3",
    "root_cause": str,
    "suggested_fix": str,
    "affected_areas": list[str],
    "estimated_effort": "S" | "M" | "L",
    "labels": list[str],
    "confidence": "high" | "medium" | "low",
}
```

**Erros possíveis:**
- `LLMError`: LLM retornou JSON inválido ou provider desconhecido
- Exceptions de network do `anthropic`/`openai` (propagadas)

### `github_client.create_issue(analysis: dict, event: dict) -> dict`

**Input:** dict no schema acima + dict do evento (pra extrair URL, event_id)

**Output:** `{"number": int, "url": str}`

**Erros possíveis:**
- `RuntimeError`: faltam `GITHUB_TOKEN` ou `GITHUB_REPO` no env
- `GithubException`: erros da API (rate limit, repo não encontrado, etc)
- Se labels não existirem, faz fallback automático sem labels (não falha)

## Limites conhecidos

- **Throughput**: ~1 análise por vez por instância (BackgroundTask). Pra demo OK.
  Pra prod precisa de queue real.
- **Custo por evento**: ~$0.005-0.02 por análise dependendo do provider e tamanho do
  contexto. Pra 1000 erros/mês = $5-20.
- **Latência**: 5-10s do trigger até issue no GitHub. Aceitável pra "bug fixing
  proativo" (compare com horas de triagem manual).
- **Sem deduplicação**: cada novo evento gera nova issue. O Sentry agrupa erros em
  issues, então o webhook só dispara em **issue NOVA** por padrão (não em ocorrência
  adicional). Isso já evita spam.

## Pontos de extensão futuros (não implementar agora)

- **Slack notification** após criar issue (1 chamada extra ao final do `_process_webhook`)
- **Filtro por severidade** antes de criar issue (não cria pra P3, por exemplo)
- **Re-análise** quando issue já existe e nova ocorrência chega (Sentry tem `event_alert`
  além de `issue_alert`)
- **HMAC verification** do webhook (header `Sentry-Hook-Signature`)
- **Análise comparativa** com issues passadas (RAG simples no LLM)
