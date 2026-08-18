"""Regras de contato usadas pela API."""


def normalizar_telefone(raw_phone: str) -> int:
    """Normaliza telefone removendo caracteres não numéricos."""
    digits = "".join(filter(str.isdigit, str(raw_phone)))
    if not digits:
        raise ValueError("Telefone sem dígitos pra normalizar")
    return int(digits)
