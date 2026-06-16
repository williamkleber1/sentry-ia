"""Helper do consumidor de batch."""


def primeira_mensagem(mensagens: list[dict]) -> str | None:
    """Retorna o body da primeira mensagem, ou None se o batch vier vazio."""
    if not mensagens:
        return None
    return mensagens[0].get("body")
