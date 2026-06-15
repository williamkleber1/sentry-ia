"""Configurações lidas do .env."""
import os
from dotenv import load_dotenv

load_dotenv()

# Sentry
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "demo")
SENTRY_CLIENT_SECRET = os.getenv("SENTRY_CLIENT_SECRET", "")

# LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude").lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")

# App
APP_PORT = int(os.getenv("APP_PORT", "8000"))
