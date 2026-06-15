# Demo Day — 16/06/2026

Checklist e plano de ação pro dia da palestra. Se algo dá errado durante a demo,
essa é sua referência rápida.

## Na véspera (15/06 à noite)

- [ ] Testar fluxo completo end-to-end uma última vez
- [ ] Gravar **vídeo de backup** da POC funcionando (3 takes, escolhe o melhor)
- [ ] Salvar o vídeo no notebook E no celular (redundância)
- [ ] Verificar bateria do notebook e levar carregador
- [ ] Confirmar acesso ao WiFi do local da apresentação
- [ ] **Habilitar 4G/hotspot do celular** como backup de internet
- [ ] Dormir cedo

## Setup pré-palestra (~30min antes)

### Stack de comandos pra rodar

Abrir 3 terminais:

**Terminal 1 — servidor:**
```bash
cd ~/sentry-ai-poc
source .venv/bin/activate
uvicorn app.main:app --port 8000
```

**Terminal 2 — tunnel:**
```bash
cloudflared tunnel --url http://localhost:8000
# copia a URL https://*.trycloudflare.com que aparece
```

**Terminal 3 — comandos prontos:**
```bash
# deixa esses comandos colados num arquivo .txt aberto pra copy-paste rápido
curl http://localhost:8000/trigger-error?kind=null_ref
curl http://localhost:8000/trigger-error?kind=division
curl http://localhost:8000/trigger-error?kind=type
curl http://localhost:8000/trigger-error?kind=timeout

# Plano C — direto sem Sentry:
curl -X POST http://localhost:8000/test-analyze \
  -H "Content-Type: application/json" \
  -d @scripts/test_payload.json
```

### Configurar webhook no Sentry com a URL nova do tunnel

Cada vez que reinicia o `cloudflared`, a URL muda. Você precisa atualizar:

1. Sentry → Settings → Developer Settings → seu Internal Integration
2. Webhook URL: `https://NOVA-URL.trycloudflare.com/sentry-webhook`
3. Save

Dá um teste rápido pra ver se chega:

```bash
curl -X POST https://NOVA-URL.trycloudflare.com/healthz
# deve retornar {"status":"ok"}
```

### Abas do navegador na ordem

Janela 1 (compartilhada na projeção, NÃO maximizada — ~80% da tela):

1. Terminal 1 (uvicorn) — verá os logs ao vivo
2. https://sentry.io/organizations/SUA_ORG/issues/ — dashboard de issues
3. https://github.com/SEU_USER/sentry-ai-demo/issues — board de cards
4. (oculta) Vídeo de backup pronto pra tocar

Zoom do navegador em **125%** pra ficar legível na projeção.

### Checklist final (5 min antes)

- [ ] Servidor rodando, sem erros nos logs
- [ ] Tunnel ativo, URL fixa
- [ ] Webhook no Sentry atualizado e testado
- [ ] Notebook conectado ao projetor
- [ ] Volume do som no zero (não quer notificação tocando)
- [ ] Slack/Discord/email fechados (sem notificações)
- [ ] Não dormiu (modo "no sleep" ativado)

## Durante a demo

Roteiro detalhado em `docs/ROTEIRO_DEMO.md`. Aqui só os pontos críticos:

### Comandos exatos a digitar (na ordem)

1. **Abrir terminal e digitar (ou usar histórico ↑):**
   ```bash
   curl http://localhost:8000/trigger-error?kind=null_ref
   ```

2. **Cmd+Tab pra aba do Sentry, dar refresh** — issue aparece em ~5s.

3. **Cmd+Tab pra aba do terminal do uvicorn** — mostrar os logs:
   ```
   INFO Webhook recebido
   INFO Chamando LLM (claude)...
   INFO Análise: severity=P1, effort=S
   INFO Issue criada: https://github.com/...
   ```

4. **Cmd+Tab pra aba do GitHub** — refresh — abrir issue nova.

## Planos B/C/D — se algo der errado

### Plano B: Webhook não dispara, mas servidor está OK
- Use `/test-analyze` direto:
  ```bash
  curl -X POST http://localhost:8000/test-analyze \
    -H "Content-Type: application/json" -d @scripts/test_payload.json
  ```
- Narrativa: "vou simular o payload que o Sentry mandaria, na real ele chega
  automaticamente"

### Plano C: LLM dá erro/rate limit
- Tenha um screenshot da última análise bem-sucedida salvo no desktop
- "Acabei de bater o limit do plano free, mas olha aqui o resultado que tive ontem"
- Mostra screenshot

### Plano D: Internet caiu completamente
- Toca o vídeo de backup
- "Pelo visto a internet escolheu o pior momento. Deixa eu te mostrar o que gravei
  ontem rodando."

### Plano E: Notebook trava
- Saca o celular, abre o vídeo lá
- "Né o ideal, mas resolve"

## Frases-âncora pra memorizar

Repete em voz baixa antes da demo, vai te tirar de qualquer brancos:

- "A gente automatizou tudo, menos a interpretação."
- "Dado bruto não é ação."
- "O dev sai do passo 1 e vai pro passo 3."
- "De alerta a card, sem ninguém no meio."

## Perguntas frequentes pra estar preparado

**"Quanto custa?"**
> Por evento, custa centavos. Claude Sonnet em ~3K tokens sai por ~$0.009. Pra 1000
> erros únicos/mês são $9/mês. Bem mais barato que a hora do dev investigando.

**"E se o LLM alucinar?"**
> O card tem um campo `confidence: high/medium/low` que o próprio LLM declara. Cards
> com confidence baixa vão pra label diferente, dev sabe que precisa olhar com mais
> cuidado.

**"Privacidade dos dados?"**
> Esse é exatamente um dos motivos pra fazer custom em vez de usar o Seer oficial.
> O contexto que vai pro LLM você controla — anonimização de PII, Claude com no-training,
> ou rodar Llama local. Já temos LiteLLM em discussão pro Lead e Gaia.

**"Quando vão pra produção?"**
> Por enquanto é POC pra mostrar viabilidade. Próximo passo é discutir com o time e
> com o Rafael qual seria o piloto. Pensei no broker do WhatsApp como bom candidato —
> é alto volume e a gente já tem o Sentry rodando lá.

**"Diferença pro Sentry Seer?"**
> Existe e é ótimo, custa $40/dev/mês. Custom faz sentido pra: 1) integrar com
> board interno não-padrão, 2) controle de privacidade, 3) escolher o modelo. Pode
> até começar com Seer e migrar pra custom depois.

**"Funciona pra Java/Go/JS?"**
> Sim, qualquer linguagem que o Sentry suporta. O serviço que recebe o webhook é
> linguagem-agnóstico — só lê JSON. O prompt provavelmente precisaria de ajustes
> pra cada stack, mas a arquitetura é a mesma.

**"Demora quanto?"**
> Do erro até o card no board: 5-10 segundos. Comparado com triagem manual que
> leva minutos a horas dependendo da fila do dev.

## Pós-palestra

- [ ] Subir os slides pro local combinado (Drive, Confluence, etc.)
- [ ] Subir o código no GitHub público (com README) — facilita quem quiser tentar
- [ ] Anotar perguntas que NÃO consegui responder bem — pra estudar depois
- [ ] Pegar feedback do Rafael e do pessoal de IA
- [ ] Discutir possibilidade de piloto no broker do WhatsApp

## Lembrete final

A apresentação é técnica, mas o pessoal lá não é só dev. Tem gente de produto,
gestão, IA. Quando explicar o stack (Lambda, SQS, EventBridge), tradução pra todos:
> "Imagina uma esteira de processamento que só liga quando tem caixa nova chegando.
> É barato porque só roda quando precisa."

Quando a demo "der certo" (que vai dar), **pause 2 segundos antes de explicar o
resultado**. Deixa o impacto pousar. O silêncio depois do card aparecer no GitHub
vale ouro.

Boa palestra. Você se preparou. 🚀
