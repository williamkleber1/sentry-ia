#!/usr/bin/env python3
"""Roda o fluxo completo localmente, SEM precisar do Sentry configurado.

Use durante desenvolvimento pra iterar rápido no prompt e na análise.

Uso:
    python scripts/test_local.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import llm, github_client


def main():
    payload_path = Path(__file__).parent / "test_payload.json"
    with open(payload_path) as f:
        payload = json.load(f)

    print("=" * 60)
    print("🧪 TESTE LOCAL — fluxo completo sem Sentry")
    print("=" * 60)

    print("\n1️⃣  Chamando LLM pra analisar o erro...")
    analysis = llm.analyze_event(payload)

    print("\n📋 ANÁLISE GERADA:")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

    print("\n2️⃣  Criando issue no GitHub...")
    try:
        issue = github_client.create_issue(analysis, payload["event"])
        print(f"\n✅ Issue criada: {issue['url']}")
    except Exception as e:
        print(f"\n⚠️  Erro ao criar issue: {e}")
        print("   (Talvez GITHUB_TOKEN/GITHUB_REPO não estejam configurados — análise gerada acima)")


if __name__ == "__main__":
    main()
