#!/usr/bin/env bash
# ============================================================================
#  CHEAT SHEET DE DEMO — Sentry + IA
# ============================================================================
#  Todos os curls estão COMENTADOS de propósito. Na hora da apresentação,
#  descomente a linha do cenário que quiser e cole no terminal (ou rode a linha).
#
#  Pré-requisitos:
#    - Servidor no ar:  .venv/bin/uvicorn app.main:app --port 8000
#    - (fluxo real) ngrok + webhook do Sentry configurados
#
#  Dois caminhos:
#    1) FLUXO REAL  -> /trigger-error : erro vai pro Sentry, o webhook chama a
#       POC e o card nasce sozinho no board (~30-40s). É o showpiece.
#    2) INSTANTÂNEO -> /demo/run      : dispara + analisa + cria card na hora e
#       devolve a análise no terminal. Dá pra escolher provider e Copilot.
# ============================================================================

BASE="http://localhost:8000"

# ----------------------------------------------------------------------------
# 1) FLUXO REAL — erro proposital -> Sentry -> webhook -> card
#    (retorna HTTP 500: é o erro de verdade; o card aparece no board em ~30-40s)
# ----------------------------------------------------------------------------

# KeyError — cliente sem o campo 'email' no contexto
# curl "$BASE/trigger-error?kind=null_ref"

# ZeroDivisionError — taxa média com zero usuários ativos
# curl "$BASE/trigger-error?kind=division"

# TypeError — soma de string com int no parsing do payload
# curl "$BASE/trigger-error?kind=type"

# TimeoutError — API do Genesys Cloud não respondeu em 30s
# curl "$BASE/trigger-error?kind=timeout"

# IndexError — primeiro item de um batch vazio da fila
# curl "$BASE/trigger-error?kind=index"

# ValueError — int() num telefone com '+' e caractere inválido
# curl "$BASE/trigger-error?kind=value"

# ConnectionError — Redis fora do ar ao carregar o contexto da conversa
# curl "$BASE/trigger-error?kind=connection"

# JSONDecodeError — corpo do webhook não é JSON válido
# curl "$BASE/trigger-error?kind=json"

# AttributeError — contato não encontrado (None) e chamou .lower()
# curl "$BASE/trigger-error?kind=none_attr"

# PermissionError — token de serviço do Genesys expirou (401)
# curl "$BASE/trigger-error?kind=genesys_auth"

# UnicodeDecodeError — caption de mídia em encoding inválido
# curl "$BASE/trigger-error?kind=unicode"


# ----------------------------------------------------------------------------
# 2) INSTANTÂNEO — /demo/run (escolhe provider e Copilot, vê a análise na hora)
#    body: {"kind": "...", "provider": "github|jira", "copilot": true|false}
#    Troque o kind por qualquer um da lista acima.
# ----------------------------------------------------------------------------

# --- Card no GitHub Issues ---
# curl -s -X POST "$BASE/demo/run" -H "Content-Type: application/json" \
#   -d '{"kind":"connection","provider":"github","copilot":false}' | python3 -m json.tool

# --- Card no Jira (projeto KAN) ---
# curl -s -X POST "$BASE/demo/run" -H "Content-Type: application/json" \
#   -d '{"kind":"timeout","provider":"jira","copilot":false}' | python3 -m json.tool

# --- BÔNUS: GitHub + Copilot abre o PR (copilot só funciona no GitHub) ---
# curl -s -X POST "$BASE/demo/run" -H "Content-Type: application/json" \
#   -d '{"kind":"none_attr","provider":"github","copilot":true}' | python3 -m json.tool


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------

# Lista os cenários disponíveis
# curl -s "$BASE/scenarios" | python3 -m json.tool

# Status do PR do Copilot pra uma issue (troque o número)
# curl -s "$BASE/demo/pr-status?number=13" | python3 -m json.tool

# Health check
# curl -s "$BASE/healthz"
