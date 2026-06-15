"""Abstração de provider de LLM — Claude ou OpenAI via env."""
import json
import logging
from typing import Any

from app import config
from app.prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Erro ao chamar o LLM."""


def _extract_json(text: str) -> dict:
    """Extrai JSON da resposta do LLM (tolera cercas de código residuais)."""
    text = text.strip()
    # Remove cerca de código se o LLM teimou em colocar
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM retornou JSON inválido: {e}\n---\n{text[:500]}")


def _call_claude(user_prompt: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return resp.content[0].text


def _call_openai(user_prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        max_tokens=1500,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def _call_mock(user_prompt: str) -> str:
    """Análise canned pra testar o fluxo sem gastar API (LLM_PROVIDER=mock).

    Devolve um JSON fixo no cenário do test_payload.json (KeyError genesys).
    Serve pra ensaiar a demo offline e validar a criação do card.
    """
    analysis = {
        "title": "[KeyError] genesys_session_id ausente no contexto de roteamento",
        "severity": "P1",
        "root_cause": (
            "O contexto da conversa carregado do Redis não contém a chave "
            "'genesys_session_id' em algumas mensagens (provavelmente conversas "
            "iniciadas antes da sessão Genesys ser criada). O roteador acessa "
            "ctx['genesys_session_id'] direto, sem checar a existência da chave."
        ),
        "suggested_fix": (
            "Trocar o acesso direto por `.get()` com fallback e tratar o caso de "
            "sessão ausente:\n\n"
            "```python\n"
            "session_id = ctx.get('genesys_session_id')\n"
            "if not session_id:\n"
            "    # cria/recupera a sessão Genesys antes de rotear\n"
            "    session_id = genesys.ensure_session(ctx)\n"
            "```"
        ),
        "affected_areas": [
            "app/services/genesys_router.py",
            "app/handlers/whatsapp_handler.py",
        ],
        "estimated_effort": "S",
        "labels": ["bug", "backend", "whatsapp-broker"],
        "confidence": "high",
    }
    return json.dumps(analysis, ensure_ascii=False)


def analyze_event(event: dict[str, Any]) -> dict[str, Any]:
    """Recebe payload do Sentry, retorna análise estruturada do LLM."""
    user_prompt = build_user_prompt(event)
    logger.info(f"Chamando LLM ({config.LLM_PROVIDER})...")

    if config.LLM_PROVIDER == "claude":
        raw = _call_claude(user_prompt)
    elif config.LLM_PROVIDER == "openai":
        raw = _call_openai(user_prompt)
    elif config.LLM_PROVIDER == "mock":
        raw = _call_mock(user_prompt)
    else:
        raise LLMError(f"Provider não suportado: {config.LLM_PROVIDER}")

    analysis = _extract_json(raw)
    logger.info(f"Análise recebida: severity={analysis.get('severity')}, "
                f"effort={analysis.get('estimated_effort')}")
    return analysis
