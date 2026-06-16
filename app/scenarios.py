"""Cenários de erro pra demo — cada um com descrição + um event sintético estilo Sentry.

Usado pelo painel (/) e pelo endpoint síncrono (/demo/run):
- o `event` sintético alimenta o LLM e o card (análise rica e determinística)
- `raise_scenario(kind)` executa o bug de verdade, pra ser capturado pelo Sentry
"""
from typing import Any
from app.handlers.batch import primeira_mensagem

_PROJECT = "whatsapp-broker"
_REQUEST = {
    "method": "POST",
    "url": "https://api.hitss.com/webhooks/whatsapp",
    "headers": [["user-agent", "WhatsApp/Cloud-API"], ["content-type", "application/json"]],
}


def _event(kind: str, exc_type: str, value: str, frames: list[dict],
           breadcrumbs: list[dict], tags: list[list[str]]) -> dict[str, Any]:
    """Monta um payload de evento no formato que o build_user_prompt espera."""
    return {
        "event_id": f"demo-{kind}",
        "project": _PROJECT,
        "environment": "production",
        "release": "broker@2.4.1",
        "platform": "python",
        "event_count": 1,
        "user_count": 1,
        "url": f"https://williams-ah.sentry.io/issues/?query=demo-{kind}",
        "exception": {"values": [{"type": exc_type, "value": value,
                                  "stacktrace": {"frames": frames}}]},
        "breadcrumbs": {"values": breadcrumbs},
        "request": _REQUEST,
        "tags": tags,
    }


def _crumb(cat: str, msg: str, level: str = "info") -> dict:
    return {"timestamp": "2026-06-14T22:00:00Z", "category": cat, "message": msg, "level": level}


# Cada cenário: kind, emoji, label (curto), description (pro painel), event (sintético)
SCENARIOS: list[dict[str, Any]] = [
    {
        "kind": "null_ref", "emoji": "🗃️", "label": "KeyError",
        "description": "Acesso a chave inexistente: o contexto do cliente não tem o campo 'email'.",
        "event": _event("null_ref", "KeyError", "'email'",
            [{"filename": "app/handlers/whatsapp_handler.py", "lineno": 142, "function": "process_inbound",
              "context_line": "email = cliente['email'].lower()"}],
            [_crumb("db", "Buscando cliente no Redis"), _crumb("cache", "Cache miss, indo no DB", "warning")],
            [["service", "whatsapp-broker"], ["region", "us-east-1"], ["customer_id", "acme-corp"]]),
    },
    {
        "kind": "division", "emoji": "➗", "label": "ZeroDivisionError",
        "description": "Divisão por zero ao calcular taxa média quando não há usuários ativos.",
        "event": _event("division", "ZeroDivisionError", "division by zero",
            [{"filename": "app/services/metrics.py", "lineno": 58, "function": "taxa_media",
              "context_line": "return total / len(usuarios_ativos)"}],
            [_crumb("business", "Calculando taxa média por usuário")],
            [["service", "metrics-worker"], ["region", "us-east-1"]]),
    },
    {
        "kind": "type", "emoji": "🔤", "label": "TypeError",
        "description": "Soma de string com int no parsing de um campo numérico do payload.",
        "event": _event("type", "TypeError", "can only concatenate str (not \"int\") to str",
            [{"filename": "app/handlers/parser.py", "lineno": 74, "function": "parse_payload",
              "context_line": "idade_proximo_ano = payload['idade'] + 1"}],
            [_crumb("parsing", "Parseando payload do webhook")],
            [["service", "whatsapp-broker"]]),
    },
    {
        "kind": "timeout", "emoji": "⏱️", "label": "TimeoutError",
        "description": "Chamada à API do Genesys Cloud estourou o timeout de 30s.",
        "event": _event("timeout", "TimeoutError", "Genesys API não respondeu em 30s",
            [{"filename": "app/services/genesys_router.py", "lineno": 103, "function": "route_message",
              "context_line": "resp = httpx.post(GENESYS_URL, json=body, timeout=30)"}],
            [_crumb("http", "Chamando API externa do Genesys")],
            [["service", "genesys-router"], ["region", "us-east-1"]]),
    },
    {
        "kind": "index", "emoji": "📑", "label": "IndexError",
        "description": "Lista de mensagens vazia: acesso ao primeiro item de um batch sem itens.",
        "event": _event("index", "IndexError", "list index out of range",
            [{"filename": "app/handlers/batch.py", "lineno": 39, "function": "primeira_mensagem",
              "context_line": "if not mensagens: return None"}],
            [_crumb("queue", "Consumindo batch da fila SQS"), _crumb("business", "Batch chegou vazio", "warning")],
            [["service", "batch-consumer"]]),
    },
    {
        "kind": "value", "emoji": "🔢", "label": "ValueError",
        "description": "Conversão de telefone pra int falha quando vem com '+' e dígitos não numéricos.",
        "event": _event("value", "ValueError", "invalid literal for int() with base 10: '+5511x9999'",
            [{"filename": "app/handlers/contato.py", "lineno": 27, "function": "normalizar_telefone",
              "context_line": "numero = int(raw_phone)"}],
            [_crumb("parsing", "Normalizando telefone do contato")],
            [["service", "whatsapp-broker"]]),
    },
    {
        "kind": "connection", "emoji": "🔌", "label": "ConnectionError",
        "description": "Redis fora do ar: conexão recusada ao carregar o contexto da conversa.",
        "event": _event("connection", "ConnectionError", "Error 111 connecting to redis:6379. Connection refused.",
            [{"filename": "app/services/context_store.py", "lineno": 45, "function": "carregar_contexto",
              "context_line": "return self.redis.get(f'ctx:{conversa_id}')"}],
            [_crumb("cache", "Conectando no Redis"), _crumb("cache", "Connection refused", "error")],
            [["service", "context-store"], ["region", "us-east-1"]]),
    },
    {
        "kind": "json", "emoji": "📦", "label": "JSONDecodeError",
        "description": "Payload malformado: corpo do webhook não é um JSON válido.",
        "event": _event("json", "JSONDecodeError", "Expecting value: line 1 column 1 (char 0)",
            [{"filename": "app/api/webhooks.py", "lineno": 58, "function": "whatsapp_webhook",
              "context_line": "data = json.loads(request.body)"}],
            [_crumb("http", "Recebendo POST /webhooks/whatsapp")],
            [["service", "whatsapp-broker"]]),
    },
    {
        "kind": "none_attr", "emoji": "🫥", "label": "AttributeError",
        "description": "Contato não encontrado retornou None e o código chamou .lower() nele.",
        "event": _event("none_attr", "AttributeError", "'NoneType' object has no attribute 'lower'",
            [{"filename": "app/handlers/contato.py", "lineno": 51, "function": "buscar_nome",
              "context_line": "return contato_nome.lower()"}],
            [_crumb("db", "Buscando contato por telefone"), _crumb("db", "Contato não encontrado (None)", "warning")],
            [["service", "whatsapp-broker"]]),
    },
    {
        "kind": "genesys_auth", "emoji": "🔐", "label": "PermissionError (Genesys 401)",
        "description": "Token de serviço do Genesys Cloud expirou — chamada voltou 401 Unauthorized.",
        "event": _event("genesys_auth", "PermissionError", "Genesys Cloud retornou 401: token de serviço expirado",
            [{"filename": "app/services/genesys_router.py", "lineno": 67, "function": "ensure_session",
              "context_line": "raise PermissionError(f'Genesys retornou {resp.status_code}: token expirado')"}],
            [_crumb("auth", "Renovando token do Genesys"), _crumb("http", "POST /conversations -> 401", "error")],
            [["service", "genesys-router"], ["region", "us-east-1"]]),
    },
    {
        "kind": "unicode", "emoji": "🧬", "label": "UnicodeDecodeError",
        "description": "Caption de mídia veio em encoding inválido e quebrou o decode UTF-8.",
        "event": _event("unicode", "UnicodeDecodeError", "'utf-8' codec can't decode byte 0xff in position 0",
            [{"filename": "app/handlers/media.py", "lineno": 88, "function": "ler_caption",
              "context_line": "return raw_caption.decode('utf-8')"}],
            [_crumb("media", "Baixando mídia do WhatsApp"), _crumb("parsing", "Decodificando caption")],
            [["service", "media-worker"]]),
    },
]

_BY_KIND = {s["kind"]: s for s in SCENARIOS}


def get(kind: str) -> dict[str, Any] | None:
    return _BY_KIND.get(kind)


def raise_scenario(kind: str) -> None:
    """Executa o bug de verdade — pra ser capturado pelo Sentry (dashboard)."""
    if kind == "null_ref":
        cliente = {"nome": "João"}
        _ = cliente["email"]
    elif kind == "division":
        usuarios_ativos: list = []
        _ = 100 / len(usuarios_ativos)
    elif kind == "type":
        _ = "42" + 1  # type: ignore[operator]
    elif kind == "timeout":
        raise TimeoutError("Genesys API não respondeu em 30s")
    elif kind == "index":
        mensagens: list[dict] = []
        _ = primeira_mensagem(mensagens)
    elif kind == "value":
        _ = int("+5511x9999")
    elif kind == "connection":
        raise ConnectionError("Error 111 connecting to redis:6379. Connection refused.")
    elif kind == "json":
        import json
        json.loads("not json")
    elif kind == "none_attr":
        nome = None
        _ = nome.lower()  # type: ignore[union-attr]
    elif kind == "genesys_auth":
        raise PermissionError("Genesys Cloud retornou 401: token de serviço expirado")
    elif kind == "unicode":
        b"\xff\xfe".decode("utf-8")
    else:
        raise ValueError(f"kind desconhecido: {kind}")
