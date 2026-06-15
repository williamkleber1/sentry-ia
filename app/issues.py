"""Despacha a criação do card pro provider configurado (github | jira).

Mantém a mesma interface dos dois clientes: create_issue(analysis, event) -> {number, url}.
Import preguiçoso pra não exigir o package do provider que não está em uso.
"""
import logging
from typing import Any

from app import config

logger = logging.getLogger(__name__)


def create_issue(analysis: dict[str, Any], event: dict[str, Any],
                  provider: str | None = None, assign_copilot: bool | None = None) -> dict[str, Any]:
    """Cria o card no board escolhido. `provider`/`assign_copilot` sobrescrevem o .env por requisição."""
    provider = (provider or config.ISSUE_PROVIDER).lower()
    logger.info(f"Criando card no provider: {provider}")

    if provider == "github":
        from app import github_client
        return github_client.create_issue(analysis, event, assign_copilot=assign_copilot)
    if provider == "jira":
        # Copilot é só GitHub — ignorado no Jira
        from app import jira_client
        return jira_client.create_issue(analysis, event)

    raise RuntimeError(f"ISSUE_PROVIDER não suportado: {provider}")
