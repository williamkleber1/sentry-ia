"""Cliente GitHub — cria issue com a análise da IA formatada."""
import logging
from typing import Any

from github import Github, GithubException

from app import config

logger = logging.getLogger(__name__)


def _format_issue_body(analysis: dict[str, Any], event: dict[str, Any]) -> str:
    """Formata o corpo do issue em markdown, com a análise da IA + link Sentry."""
    sentry_url = event.get("url") or event.get("web_url") or ""
    event_id = event.get("event_id", "N/A")

    severity_emoji = {
        "P0": "🚨", "P1": "🔴", "P2": "🟡", "P3": "🔵"
    }.get(analysis.get("severity", "P2"), "⚪")

    confidence = analysis.get("confidence", "medium")
    conf_emoji = {"high": "🎯", "medium": "🎲", "low": "❓"}.get(confidence, "🎲")

    body = f"""> 🤖 **Card criado automaticamente pela análise de IA do Sentry**
> Event ID: `{event_id}` · Confiança da análise: {conf_emoji} `{confidence}`

## {severity_emoji} Severidade: **{analysis.get('severity', 'P2')}**

## 🔍 Causa Raiz Provável
{analysis.get('root_cause', 'Sem análise.')}

## 🔧 Sugestão de Correção
{analysis.get('suggested_fix', 'Sem sugestão.')}

## 📍 Áreas Afetadas
{chr(10).join(f"- `{a}`" for a in analysis.get('affected_areas', []))}

## ⏱️ Esforço Estimado
**{analysis.get('estimated_effort', 'M')}**

---

🔗 [Ver evento original no Sentry]({sentry_url})

<sub>Gerado em: Comunidade IA · Hitss · POC Sentry+IA</sub>
"""
    return body


def create_issue(analysis: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Cria issue no GitHub com a análise. Retorna {number, url}."""
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        raise RuntimeError("GITHUB_TOKEN e GITHUB_REPO precisam estar no .env")

    title = analysis.get("title", "Erro detectado pelo Sentry")
    body = _format_issue_body(analysis, event)
    labels = analysis.get("labels", []) + [
        "sentry-ai",
        f"severity:{analysis.get('severity', 'P2').lower()}",
    ]

    gh = Github(config.GITHUB_TOKEN)
    try:
        repo = gh.get_repo(config.GITHUB_REPO)
        issue = repo.create_issue(title=title, body=body, labels=labels)
        logger.info(f"Issue #{issue.number} criada: {issue.html_url}")
        return {"number": issue.number, "url": issue.html_url}
    except GithubException as e:
        # Labels podem não existir — tenta sem
        if "label" in str(e).lower():
            logger.warning("Labels não existem no repo, criando sem labels")
            issue = repo.create_issue(title=title, body=body)
            return {"number": issue.number, "url": issue.html_url}
        raise
