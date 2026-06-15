"""Cliente Jira — cria issue com a análise da IA. Mesma interface do github_client.

Usa o gateway api.atlassian.com (REST v3 + ADF), que é o que funciona com os
tokens de API "com escopo" do Atlassian (os clássicos sem escopo estão sendo
descontinuados). Auth = Basic (email + token), escopo write:jira-work.
"""
import logging
import re
from typing import Any

import httpx

from app import config

logger = logging.getLogger(__name__)

# severity (nosso schema) -> priority (nomes padrão do Jira)
_PRIORITY = {"P0": "Highest", "P1": "High", "P2": "Medium", "P3": "Low"}
_EMOJI = {"P0": "🚨", "P1": "🔴", "P2": "🟡", "P3": "🔵"}


def _cloud_id() -> str:
    """Descobre o cloudId do site (endpoint público, sem auth)."""
    r = httpx.get(f"{config.JIRA_URL}/_edge/tenant_info", timeout=20)
    r.raise_for_status()
    return r.json()["cloudId"]


# --- helpers de ADF (Atlassian Document Format) ---
def _text(s: str) -> dict:
    return {"type": "text", "text": s}


def _heading(s: str, level: int = 3) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": [_text(s)]}


def _para(s: str) -> dict:
    return {"type": "paragraph", "content": [_text(s)] if s else []}


def _fix_blocks(text: str) -> list[dict]:
    """Quebra a sugestão de fix em parágrafos + codeBlock a partir das cercas ```."""
    parts = re.split(r"```(\w+)?\n(.*?)```", text, flags=re.DOTALL)
    blocks: list[dict] = []
    if parts[0].strip():
        blocks.append(_para(parts[0].strip()))
    idx = 1
    while idx + 1 < len(parts):  # triplas (lang, code, texto_depois)
        lang, code = parts[idx], parts[idx + 1]
        after = parts[idx + 2] if idx + 2 < len(parts) else ""
        attrs = {"language": lang} if lang else {}
        blocks.append({"type": "codeBlock", "attrs": attrs, "content": [_text(code.rstrip("\n"))]})
        if after.strip():
            blocks.append(_para(after.strip()))
        idx += 3
    return blocks or [_para(text)]


def _adf(analysis: dict[str, Any], event: dict[str, Any]) -> dict:
    """Monta a descrição como documento ADF (Jira REST v3 não aceita markdown)."""
    sev = analysis.get("severity", "P2")
    content: list[dict] = [
        _heading(f"{_EMOJI.get(sev, '⚪')} Severidade: {sev}", 2),
        _heading("🔍 Causa Raiz Provável"),
        _para(analysis.get("root_cause", "Sem análise.")),
        _heading("🔧 Sugestão de Correção"),
        *_fix_blocks(analysis.get("suggested_fix", "Sem sugestão.")),
        _heading("📍 Áreas Afetadas"),
    ]
    areas = analysis.get("affected_areas", [])
    if areas:
        content.append({"type": "bulletList", "content": [
            {"type": "listItem", "content": [_para(a)]} for a in areas]})
    else:
        content.append(_para("(não identificadas)"))

    content.append(_heading(f"⏱️ Esforço Estimado: {analysis.get('estimated_effort', 'M')}"))
    content.append({"type": "rule"})
    eid = event.get("event_id", "N/A")
    content.append(_para(
        f"🤖 Card criado automaticamente pela análise de IA do Sentry · "
        f"Event ID: {eid} · Confiança: {analysis.get('confidence', 'medium')}"
    ))
    sentry_url = event.get("url") or event.get("web_url")
    if sentry_url:
        content.append({"type": "paragraph", "content": [
            {"type": "text", "text": "Ver evento original no Sentry",
             "marks": [{"type": "link", "attrs": {"href": sentry_url}}]}]})
    return {"type": "doc", "version": 1, "content": content}


def _build_labels(analysis: dict[str, Any]) -> list[str]:
    """Labels do Jira não aceitam espaço — troca por hífen."""
    raw = analysis.get("labels", []) + ["sentry-ai", f"severity-{analysis.get('severity', 'P2').lower()}"]
    return [re.sub(r"\s+", "-", str(l)) for l in raw]


def create_issue(analysis: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Cria issue no Jira com a análise. Retorna {number, url}."""
    if not (config.JIRA_URL and config.JIRA_EMAIL and config.JIRA_TOKEN and config.JIRA_PROJECT):
        raise RuntimeError("JIRA_URL, JIRA_EMAIL, JIRA_TOKEN e JIRA_PROJECT precisam estar no .env")

    base = f"https://api.atlassian.com/ex/jira/{_cloud_id()}/rest/api/3"
    auth = (config.JIRA_EMAIL, config.JIRA_TOKEN)

    fields_base = {
        "project": {"key": config.JIRA_PROJECT},
        "summary": analysis.get("title", "Erro detectado pelo Sentry")[:255],
        "issuetype": {"name": config.JIRA_ISSUE_TYPE},
        "description": _adf(analysis, event),
    }
    labels = _build_labels(analysis)
    priority = _PRIORITY.get(analysis.get("severity", "P2"), "Medium")

    # Tenta com tudo; degrada se priority/labels não estiverem na tela do projeto
    attempts = [
        {**fields_base, "priority": {"name": priority}, "labels": labels},
        {**fields_base, "labels": labels},
        fields_base,
    ]
    last: httpx.Response | None = None
    for fields in attempts:
        r = httpx.post(f"{base}/issue", auth=auth, json={"fields": fields}, timeout=30)
        if r.status_code in (200, 201):
            key = r.json()["key"]
            logger.info(f"Issue {key} criada: {config.JIRA_URL}/browse/{key}")
            return {"number": key, "url": f"{config.JIRA_URL}/browse/{key}"}
        last = r
        logger.warning(f"Tentativa falhou ({r.status_code}), degradando campos: {r.text[:200]}")
    raise RuntimeError(f"Falha ao criar issue no Jira: {last.status_code} {last.text[:300]}")
