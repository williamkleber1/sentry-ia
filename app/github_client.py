"""Cliente GitHub — cria issue com a análise da IA formatada."""
import logging
from typing import Any

import httpx
from github import Github, GithubException

from app import config

logger = logging.getLogger(__name__)

_GRAPHQL = "https://api.github.com/graphql"


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


def _assign_to_copilot(issue_number: int) -> None:
    """Assigna a issue pro GitHub Copilot Coding Agent, que abre um PR draft. Best-effort."""
    owner, repo = config.GITHUB_REPO.split("/", 1)
    headers = {"Authorization": f"Bearer {config.GITHUB_TOKEN}"}
    q = """query($o:String!,$r:String!,$n:Int!){
      repository(owner:$o,name:$r){
        issue(number:$n){ id }
        suggestedActors(capabilities:[CAN_BE_ASSIGNED], first:100){ nodes{ login ... on Bot { id } } }
      }}"""
    resp = httpx.post(_GRAPHQL, headers=headers,
                      json={"query": q, "variables": {"o": owner, "r": repo, "n": issue_number}}, timeout=30)
    repo_data = resp.json()["data"]["repository"]
    issue_id = repo_data["issue"]["id"]
    bot = next((n for n in repo_data["suggestedActors"]["nodes"]
                if n["login"].lower() == "copilot-swe-agent"), None)
    if not bot:
        logger.warning("Copilot não disponível como assignee — pulando assign")
        return
    m = """mutation($a:ID!,$b:ID!){
      replaceActorsForAssignable(input:{assignableId:$a, actorIds:[$b]}){
        assignable{ ... on Issue { number } } }}"""
    r2 = httpx.post(_GRAPHQL, headers=headers,
                    json={"query": m, "variables": {"a": issue_id, "b": bot["id"]}}, timeout=30)
    if r2.json().get("errors"):
        logger.warning(f"Falha ao assignar Copilot: {r2.json()['errors']}")
    else:
        logger.info(f"🤖 Issue #{issue_number} assignada pro Copilot — PR draft a caminho (~minutos)")


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
    repo = gh.get_repo(config.GITHUB_REPO)
    try:
        issue = repo.create_issue(title=title, body=body, labels=labels)
    except GithubException as e:
        if "label" in str(e).lower():  # Labels podem não existir — tenta sem
            logger.warning("Labels não existem no repo, criando sem labels")
            issue = repo.create_issue(title=title, body=body)
        else:
            raise
    logger.info(f"Issue #{issue.number} criada: {issue.html_url}")

    # Opcional: assignar pro Copilot Coding Agent gerar PR draft (default off — leva ~minutos)
    if config.ENABLE_COPILOT_ASSIGN:
        try:
            _assign_to_copilot(issue.number)
        except Exception:
            logger.exception("Falha ao assignar Copilot (issue criada mesmo assim)")

    return {"number": issue.number, "url": issue.html_url}
