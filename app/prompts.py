"""Engenharia de prompt — onde a IA vira útil de verdade.

A diferença entre 'jogar stack trace pro LLM' e 'analisar erro como dev sênior'
está toda aqui. Esse é o ponto que você quer destacar na palestra.
"""

SYSTEM_PROMPT = """Você é um engenheiro de software sênior analisando um erro de \
produção capturado pelo Sentry. Sua tarefa é diagnosticar o problema com base no \
contexto fornecido e propor uma correção acionável.

Princípios:
- Seja objetivo e técnico. Sem preâmbulo.
- Quando sugerir código, use snippets curtos e diretos.
- Se a causa raiz não estiver clara, declare isso explicitamente e proponha \
investigação adicional.
- Estime severidade baseado em frequência, usuários afetados e área crítica.

Responda APENAS com JSON válido no schema fornecido. Sem markdown, sem cercas \
de código, sem texto antes ou depois do JSON."""


USER_PROMPT_TEMPLATE = """## CONTEXTO DO ERRO

**Tipo:** {exception_type}
**Mensagem:** {message}
**Projeto:** {project}
**Ambiente:** {environment}
**Release:** {release}
**Plataforma:** {platform}

**Frequência:** {event_count} ocorrências
**Usuários afetados:** {affected_users}
**Primeira ocorrência:** {first_seen}
**Última ocorrência:** {last_seen}

## STACK TRACE
```
{stack_trace}
```

## BREADCRUMBS (últimas ações antes do erro)
{breadcrumbs}

## REQUEST CONTEXT
{request_info}

## TAGS
{tags}

---

Analise o erro acima e retorne um JSON com este schema EXATO:

{{
  "title": "string — título conciso pro card, máx 80 chars. Formato: '[Tipo] descrição'",
  "severity": "P0 | P1 | P2 | P3 — P0=sistema parado, P1=degradado, P2=bug normal, P3=cosmético",
  "root_cause": "string — hipótese da causa raiz em 2-3 linhas",
  "suggested_fix": "string — sugestão prática de correção, com snippet de código se aplicável",
  "affected_areas": ["array de strings com áreas/módulos prováveis afetados"],
  "estimated_effort": "S | M | L — S=<2h, M=meio dia, L=>1 dia",
  "labels": ["array de labels relevantes pro card (ex: bug, backend, urgent)"],
  "confidence": "high | medium | low — sua confiança no diagnóstico"
}}

Responda APENAS com o JSON."""


def build_user_prompt(event: dict) -> str:
    """Constrói o prompt formatado a partir de um payload de evento do Sentry."""
    # Extração defensiva (Sentry varia por resource: alert rule manda data.event,
    # webhook error.created manda data.error, issue.* manda data.issue)
    inner = event.get("data", {}) or {}
    data = inner.get("event") or inner.get("error") or inner.get("issue") or event.get("event", event)
    exception_values = (data.get("exception", {}) or {}).get("values")
    if isinstance(exception_values, list) and exception_values:
        exc = exception_values[0]
    else:
        exc = {}

    # Stack trace formatado
    frames = exc.get("stacktrace", {}).get("frames", [])
    stack_lines = []
    for f in frames[-8:]:  # últimos 8 frames são os mais relevantes
        filename = f.get("filename", "?")
        lineno = f.get("lineno", "?")
        func = f.get("function", "?")
        context = f.get("context_line", "").strip()
        stack_lines.append(f"  File \"{filename}\", line {lineno}, in {func}")
        if context:
            stack_lines.append(f"    {context}")
    stack_trace = "\n".join(stack_lines) if stack_lines else "(stack trace não disponível)"

    # Breadcrumbs
    crumbs = (data.get("breadcrumbs", {}) or {}).get("values", [])
    crumb_lines = []
    for c in crumbs[-10:]:
        ts = c.get("timestamp", "")
        cat = c.get("category", "")
        msg = c.get("message", "")
        crumb_lines.append(f"- [{ts}] {cat}: {msg}")
    breadcrumbs = "\n".join(crumb_lines) if crumb_lines else "(sem breadcrumbs)"

    # Request — headers vêm como dict (mock) ou lista de pares [k, v] (Sentry real)
    req = data.get("request", {}) or {}
    raw_headers = req.get("headers") or {}
    if isinstance(raw_headers, list):
        header_items = [(h[0], h[1]) for h in raw_headers if isinstance(h, (list, tuple)) and len(h) >= 2]
    else:
        header_items = list(raw_headers.items())
    request_info = (
        f"Method: {req.get('method', 'N/A')}\n"
        f"URL: {req.get('url', 'N/A')}\n"
        f"Headers: {dict(header_items[:5])}"
    )

    # Tags — pode vir como lista de pares [k, v] ou lista de dicts {"key","value"}
    tags = data.get("tags", []) or []
    tag_lines = []
    for t in tags:
        if isinstance(t, dict):
            k, v = t.get("key"), t.get("value")
        elif isinstance(t, (list, tuple)) and len(t) >= 2:
            k, v = t[0], t[1]
        else:
            continue
        tag_lines.append(f"  - {k}: {v}")
    tags_str = "\n".join(tag_lines[:10]) if tag_lines else "(sem tags)"

    return USER_PROMPT_TEMPLATE.format(
        exception_type=exc.get("type", "Unknown"),
        message=exc.get("value", data.get("message", "Sem mensagem")),
        project=data.get("project", "demo-app"),
        environment=data.get("environment", "demo"),
        release=data.get("release", "N/A"),
        platform=data.get("platform", "python"),
        event_count=data.get("event_count", 1),
        affected_users=data.get("user_count", 1),
        first_seen=data.get("first_seen", "N/A"),
        last_seen=data.get("last_seen", "N/A"),
        stack_trace=stack_trace,
        breadcrumbs=breadcrumbs,
        request_info=request_info,
        tags=tags_str,
    )
