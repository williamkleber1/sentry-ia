# Roteiro da Demo — 4-5 minutos

Demo ao vivo da palestra "Do alerta ao card" — Comunidade IA Hitss · 16/06/2026

## Setup ANTES de subir no palco

- [ ] Notebook conectado à internet (4G de backup ligado)
- [ ] `.env` preenchido e funcional (testou hoje cedo)
- [ ] Servidor FastAPI rodando: `uvicorn app.main:app --port 8000`
- [ ] ngrok exposto: `ngrok http 8000`
- [ ] Webhook Sentry apontando pra URL do ngrok
- [ ] Browser com 3 abas abertas na ordem:
  1. **Aba 1:** Terminal com o uvicorn rodando (mostra logs)
  2. **Aba 2:** Sentry dashboard (Issues do projeto)
  3. **Aba 3:** GitHub Issues do repo de demo
- [ ] Janela do navegador NÃO maximizada — você quer mostrar 2-3 abas ao mesmo tempo
- [ ] Zoom do navegador em ~125% pra ficar legível na projeção
- [ ] **Vídeo de backup já gravado** rodando em outra aba (caso a internet caia)

## Roteiro narrado (5 minutos)

### Minuto 1: Setup e contexto (~45s)

**Mostre Aba 1 (terminal)**

> "Eu tenho aqui um serviço FastAPI rodando localmente, parecido com o que a
> gente roda em produção. Esse serviço tem o Sentry SDK instrumentado — três
> linhas de configuração, nada demais."

[Cmd+Tab pra mostrar o código por 5 segundos]

```python
sentry_sdk.init(dsn=..., environment="demo", integrations=[FastApiIntegration()])
```

> "E aqui eu tenho um endpoint que dispara um erro proposital — é o cenário
> 'quebrei alguma coisa em produção e nem sei'."

### Minuto 2: Trigger e captura (~1min)

**Vá pra Aba 1 (terminal)**

> "Vou disparar um erro agora — KeyError em código que tenta acessar
> `genesys_session_id` num contexto que não tem essa chave. Cenário real
> de quem trabalha com integração."

[Em outra aba terminal, digite o comando — DEIXE OS OUTROS VEREM]

```bash
curl http://localhost:8000/trigger-error?kind=null_ref
```

> "500 Internal Server Error — o usuário viu um erro. Em produção, o
> cliente já tá no Slack reclamando."

**Vá pra Aba 2 (Sentry)**

> "Mas olha o que acontece em paralelo. O Sentry capturou o erro com tudo:
> stack trace, breadcrumbs dos últimos passos, request context, tags."

[Refresh na página do Sentry — issue nova aparece]

> "Até aqui, é o cenário tradicional. Stack trace pronto, dev faz triagem,
> abre card, investiga. Em média, isso leva entre 30 minutos e várias horas
> dependendo da prioridade da fila."

### Minuto 3: O webhook dispara, IA analisa (~1min30)

**Vá pra Aba 1 (terminal)**

> "Mas eu plugei um webhook do Sentry no meu serviço. Olha o log:"

[Aponte pros logs que aparecem em tempo real]

```
INFO Webhook recebido. Keys: ['event', 'project', ...]
INFO Chamando LLM (claude)...
INFO Análise recebida: severity=P1, effort=S
INFO Issue #42 criada: https://github.com/.../issues/42
```

> "Em ~10 segundos, o webhook chegou no meu Lambda local, ele montou um
> prompt estruturado com o contexto completo do erro — não só o stack
> trace, mas breadcrumbs, request, tags — e mandou pro Claude analisar
> como se fosse um dev sênior."

**Pause de 2s pra deixar o impacto pousar**

> "Olha o que voltou."

### Minuto 4: O card mágico (~1min30)

**Vá pra Aba 3 (GitHub Issues)**

[Refresh — issue nova aparece no topo]

> "Card novo no board. Título descritivo: '[KeyError] genesys_session_id
> ausente no contexto de roteamento'."

[Clique pra abrir a issue]

> "E o corpo do card:"

- 🚨 **Severidade P1** — categorizada automaticamente
- 🔍 **Causa raiz provável** — análise em prosa de 2-3 linhas
- 🔧 **Sugestão de correção** — com snippet de código
- 📍 **Áreas afetadas** — módulos prováveis identificados
- ⏱️ **Esforço estimado** — S/M/L

> "Tudo isso baseado APENAS no contexto que o Sentry coletou
> automaticamente. Nenhum dev tocou nesse card."

### Minuto 5: Encerramento (~30s)

**Volte pra Aba 1 ou pro slide**

> "O ponto não é 'a IA substitui o dev'. O ponto é: a IA tirou da minha
> frente o trabalho chato de triagem inicial. O dev que pega esse card
> já começa do passo 3, não do passo 1.
>
> E olha o mais interessante: isso já existe rodando em segundo plano.
> Não precisa lembrar de fazer triagem, não precisa ter alguém de plantão
> pra olhar o Sentry. Bug acontece, card aparece pronto. **De alerta a
> card, sem ninguém no meio.**"

[Volta pro slide de Demonstração ou avança pra Q&A]

## Plano B — se a internet falhar

1. **Reconheça calmamente:** "Show, parece que a magia da internet falhou
   no momento certo. Deixa eu te mostrar o vídeo que gravei do fluxo
   ontem rodando."
2. **Toque o vídeo** (já aberto numa aba)
3. **Comente sobre o que aparece** com o mesmo roteiro acima

## Plano C — se o LLM der erro/timeout

1. Use o endpoint `/test-analyze` com o `test_payload.json` pré-carregado
2. Comente: "Detectaram um KeyError no broker do WhatsApp" e siga

## Plano D — se o GitHub falhar

1. O endpoint `/test-analyze` retorna a análise como JSON na resposta
2. Mostre o JSON formatado no terminal — o impacto da análise da IA já
   é suficiente sem o card final

## Comandos rápidos pra ter à mão (cole num arquivo separado)

```bash
# 1. Subir o servidor (terminal 1)
cd ~/sentry-ai-poc && source .venv/bin/activate
uvicorn app.main:app --port 8000

# 2. Expor com ngrok (terminal 2)
ngrok http 8000

# 3. Trigger de erro (terminal 3)
curl http://localhost:8000/trigger-error?kind=null_ref

# 4. Alternativas de erro (caso queira variar)
curl http://localhost:8000/trigger-error?kind=division
curl http://localhost:8000/trigger-error?kind=type
curl http://localhost:8000/trigger-error?kind=timeout

# 5. Plano C — teste direto sem Sentry
curl -X POST http://localhost:8000/test-analyze \
  -H "Content-Type: application/json" \
  -d @scripts/test_payload.json
```

## Frases-âncora pra memorizar

- "A gente automatizou tudo, menos a interpretação"
- "Dado bruto não é ação"
- "O dev sai do passo 1 e vai pro passo 3"
- "De alerta a card, sem ninguém no meio"

## O que NÃO falar

- ❌ Comparações de custo específicas (você não tem números reais ainda)
- ❌ "Claude é melhor que GPT" — fica neutral, é apenas um exemplo
- ❌ Detalhes do prompt completo (deixe pra Q&A se perguntarem)
- ❌ Promessas de qual time vai adotar isso primeiro

## O que dizer se perguntarem

**"Quanto custa?"**
> "Por evento, custa centavos. O Claude Sonnet em ~3000 tokens de input
> sai por ~$0.009. Se você tem 1000 erros únicos por mês, são $9/mês.
> Bem mais barato que a hora do dev investigando."

**"E se o LLM alucinar?"**
> "Boa pergunta. O card tem um campo `confidence: high/medium/low` que o
> próprio LLM declara. Cards com confidence baixa vão pra uma label
> diferente, dev sabe que precisa olhar com mais cuidado."

**"Privacidade dos dados?"**
> "Esse é exatamente um dos motivos pra fazer custom em vez de usar o Seer
> oficial. O contexto que vai pro LLM você controla — pode anonimizar PII,
> usar Claude com flag de no-training, ou rodar Llama local."

**"Quando vocês vão colocar em produção?"**
> "Por enquanto é POC pra mostrar a viabilidade. Próximo passo é discutir
> com o time e com o Rafael qual seria o piloto."
