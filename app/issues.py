"""Despacha a criação do card pro provider configurado (github | jira).

Mantém a mesma interface dos dois clientes: create_issue(analysis, event) -> {number, url}.
Import preguiçoso pra não exigir o package do provider que não está em uso.
"""
import logging
from typing import Any

from app import config

logger = logging.getLogger(__name__)


def create_issue(analysis: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Cria o card no board configurado via ISSUE_PROVIDER."""
    provider = config.ISSUE_PROVIDER
    logger.info(f"Criando card no provider: {provider}")

    if provider == "github":
        from app import github_client
        return github_client.create_issue(analysis, event)
    if provider == "jira":
        from app import jira_client
        return jira_client.create_issue(analysis, event)

    raise RuntimeError(f"ISSUE_PROVIDER não suportado: {provider}")
