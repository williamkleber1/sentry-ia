# Demo Curls — Sentry + IA

Curls prontos pra **copiar e colar no Postman** ao vivo. URL já escrita por extenso (`http://localhost:8000`) — sem variável.

## Como importar no Postman
**New → Import → Raw text** → cola o curl → **Continue → Import**. O Postman monta a request (método, URL, headers e body) automaticamente. Clica **Send**.

> Pré-requisito: servidor no ar → `.venv/bin/uvicorn app.main:app --port 8000`
> Para o fluxo real (`/trigger-error`), o ngrok + webhook do Sentry precisam estar configurados.

---

## 1) Fluxo real — `/trigger-error`
Dispara o erro de verdade → Sentry captura → webhook → **card nasce sozinho no board (~30-40s)**.
A resposta é **HTTP 500** (é o erro real acontecendo — isso é esperado).

### 🗃️ KeyError — cliente sem o campo 'email'
```bash
curl "http://localhost:8000/trigger-error?kind=null_ref"
```

### ➗ ZeroDivisionError — taxa média com zero usuários
```bash
curl "http://localhost:8000/trigger-error?kind=division"
```

### 🔤 TypeError — soma de string com int no parsing
```bash
curl "http://localhost:8000/trigger-error?kind=type"
```

### ⏱️ TimeoutError — Genesys Cloud não respondeu em 30s
```bash
curl "http://localhost:8000/trigger-error?kind=timeout"
```

### 📑 IndexError — primeiro item de um batch vazio
```bash
curl "http://localhost:8000/trigger-error?kind=index"
```

### 🔢 ValueError — int() num telefone inválido
```bash
curl "http://localhost:8000/trigger-error?kind=value"
```

### 🔌 ConnectionError — Redis fora do ar
```bash
curl "http://localhost:8000/trigger-error?kind=connection"
```

### 📦 JSONDecodeError — corpo do webhook não é JSON válido
```bash
curl "http://localhost:8000/trigger-error?kind=json"
```

### 🫥 AttributeError — contato None e chamou .lower()
```bash
curl "http://localhost:8000/trigger-error?kind=none_attr"
```

### 🔐 PermissionError — token do Genesys expirou (401)
```bash
curl "http://localhost:8000/trigger-error?kind=genesys_auth"
```

### 🧬 UnicodeDecodeError — caption de mídia em encoding inválido
```bash
curl "http://localhost:8000/trigger-error?kind=unicode"
```

---

## 2) Instantâneo — `/demo/run`
Dispara + analisa + cria o card **na hora** e devolve a **análise em JSON** (ótimo pra mostrar no Postman).
Body: `{"kind": "...", "provider": "github|jira", "copilot": true|false}`. Troque o `kind` por qualquer um da lista acima.

### Card no GitHub Issues
```bash
curl -X POST "http://localhost:8000/demo/run" -H "Content-Type: application/json" -d "{\"kind\":\"connection\",\"provider\":\"github\",\"copilot\":false}"
```

### Card no Jira (projeto KAN)
```bash
curl -X POST "http://localhost:8000/demo/run" -H "Content-Type: application/json" -d "{\"kind\":\"timeout\",\"provider\":\"jira\",\"copilot\":false}"
```

### BÔNUS — GitHub + Copilot abre o PR (Copilot só funciona no GitHub)
```bash
curl -X POST "http://localhost:8000/demo/run" -H "Content-Type: application/json" -d "{\"kind\":\"none_attr\",\"provider\":\"github\",\"copilot\":true}"
```

---

## 3) Utilidades

### Listar os cenários disponíveis
```bash
curl "http://localhost:8000/scenarios"
```

### Status do PR do Copilot pra uma issue (troque o número)
```bash
curl "http://localhost:8000/demo/pr-status?number=13"
```

### Health check
```bash
curl "http://localhost:8000/healthz"
```
