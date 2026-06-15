# Prompt Engineering

O arquivo `app/prompts.py` é o ponto de maior alavancagem da POC. A qualidade da
demo depende mais de um prompt bom do que de qualquer outro código. Essa doc
explica como pensar nele e como iterar.

## Estrutura atual

São três peças em `app/prompts.py`:

### 1. `SYSTEM_PROMPT`
Define o **papel** do LLM e os **princípios** de resposta. Mantém o modelo focado.
Hoje:
- Papel: "engenheiro de software sênior analisando erro de produção"
- Princípios: objetivo, técnico, sem preâmbulo, código curto quando possível,
  honesto sobre incerteza
- Formato: JSON puro, sem markdown, sem cercas de código

**Por que separar de USER_PROMPT_TEMPLATE?** Porque o SYSTEM_PROMPT raramente muda
— é o "manual de identidade" do analisador. O USER_PROMPT muda a cada evento.

### 2. `USER_PROMPT_TEMPLATE`
Template formatado com `.format()`. Tem placeholders pra:
- Metadados do erro (tipo, mensagem, projeto, ambiente, release, frequência, usuários)
- Stack trace
- Breadcrumbs
- Request context
- Tags

E **define o schema do JSON de saída** no final. Esse é o ponto que mais merece
iteração — se o modelo está errando alguma campo, é aqui que você ajusta.

### 3. `build_user_prompt(event: dict)`
Faz a extração defensiva do payload do Sentry e preenche o template. Sentry payloads
variam por SDK/versão, então use sempre `.get()` com defaults — nunca acesso direto.

## Como iterar no prompt (workflow recomendado)

1. **Rode `scripts/test_local.py`** com o `scripts/test_payload.json` mock.
2. **Veja o JSON que o LLM produziu** no output.
3. **Identifique o problema**: campo errado, severidade conservadora demais, fix
   genérico demais, etc.
4. **Edite `prompts.py`** — geralmente ajustando o `USER_PROMPT_TEMPLATE` (instruções
   sobre o schema) ou o `SYSTEM_PROMPT` (princípios).
5. **Rode `test_local.py` de novo** — itere até gostar do resultado.
6. **Teste com payloads diferentes** — copie `test_payload.json` pra variantes (timeout,
   division, type) e veja se o prompt segura bem em casos diferentes.

> Sempre que mexer no prompt, rode com 2-3 payloads diferentes antes de fechar — é
> fácil "overfittar" pro caso específico que você tava testando.

## Problemas comuns e soluções

### LLM retorna JSON em markdown (```json ... ```)
O `_extract_json()` em `llm.py` já tolera isso (remove cercas). Mas se for muito
frequente, reforce no SYSTEM_PROMPT:
> "Responda APENAS JSON. Sem cercas de código. Sem texto antes. Sem texto depois."

### Severidade sempre P2 (modelo conservador)
Adicione exemplos no prompt:
> "P0 quando: sistema parado pra todos os usuários, perda de dados.
>  P1 quando: feature crítica quebrada, muitos usuários afetados.
>  P2 quando: bug em fluxo secundário, workaround disponível.
>  P3 quando: cosmético, baixa frequência, sem impacto funcional."

### `affected_areas` muito genérico ("backend", "API")
Peça especificidade:
> "affected_areas deve listar arquivos ou módulos específicos identificáveis pelo
> stack trace, não áreas genéricas. Ex: 'app/services/genesys_router.py' em vez de 'backend'."

### `suggested_fix` sem código
Reforce no prompt:
> "suggested_fix deve incluir um snippet de código (mesmo que aproximado) sempre
> que possível, usando a sintaxe da linguagem do projeto identificada nas tags."

### Modelo alucina causas sem base no stack
Adicione regra:
> "Se a causa raiz não puder ser inferida com confiança ALTA a partir do stack
> trace e breadcrumbs, declare confidence: low e diga explicitamente quais
> hipóteses você considerou."

## Engenharia do contexto (mais importante que o prompt em si)

O LLM só pode analisar o que você dá. A função `build_user_prompt()` decide isso.
Hoje extrai:

- **Stack trace**: últimos 8 frames (os mais próximos do erro). Inclui filename,
  lineno, function e context_line (a linha exata).
- **Breadcrumbs**: últimos 10. Mostra a sequência de ações antes do erro — ESSENCIAL
  pra IA entender o cenário.
- **Request context**: method, URL, headers (top 5).
- **Tags**: até 10. Tags identificam serviço, região, customer_id, etc.

### Coisas que poderiam ser adicionadas (e por que ainda não foram)

- **Trecho do código fonte**: chamada à GitHub API pra buscar as ~20 linhas em volta
  do `lineno` do top frame. **Aumenta MUITO a qualidade** da `suggested_fix`. Mas
  adiciona latência (~1-2s) e requer permissão de leitura no repo de produção.
  Vale fazer se o William quiser elevar o nível da demo.

- **Issues similares passadas**: chamada à API do Sentry pra buscar issues com mesmo
  `culprit` ou `fingerprint`. Permite contexto histórico ("esse erro já aconteceu
  3 vezes nos últimos 30 dias"). Não implementado pra não complicar.

- **Diff do último deploy**: se a tag `release` está presente, dá pra buscar o diff
  entre o último release e o anterior. Tipo "isso quebrou depois desse PR aqui".
  Bem mais complexo mas é o santo graal.

## Anatomia de um prompt bom (princípios gerais)

1. **Papel claro**: o LLM responde de forma diferente se você diz "você é um SRE"
   vs "você é um QA junior". O atual é "engenheiro de software sênior" — apropriado.

2. **Schema explícito**: sempre defina o formato de saída. Quanto mais estrutura,
   menos liberdade pro modelo errar.

3. **Princípios negativos**: "NÃO faça X" tende a ser mais eficaz que só listar
   o que fazer. Ex: "NÃO escreva preâmbulo" funciona melhor que "seja direto".

4. **Exemplos > regras abstratas**: se um campo precisa de formato específico,
   mostre 1-2 exemplos.

5. **Reserve flexibilidade pra incerteza**: o campo `confidence` é importante. Um
   modelo que sempre diz `confidence: high` está alucinando. Reforce que `low` é
   resposta aceitável e útil.

## Quando o prompt está "bom o suficiente" pra demo?

Critérios:
- ✅ JSON sempre válido (sem `JSONDecodeError` em 10 runs seguidos)
- ✅ `severity` correlaciona com impacto real (não tudo P2)
- ✅ `root_cause` identifica corretamente a linha problemática em 7 de 10 casos
- ✅ `suggested_fix` tem snippet de código quando aplicável
- ✅ `confidence: medium` ou `low` quando o stack é ambíguo (em vez de chutar `high`)

Se todos esses checks passam, está bom pra demo. Iteração além disso é refinamento.
