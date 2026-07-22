# Guia de demonstração

Abra o chat em <http://localhost:8501> e o dashboard em <http://localhost:8502>. Use o mesmo
`Session ID` nas duas telas para acompanhar a jornada automaticamente.

## Sequência recomendada

### 1. Atendimento natural

```text
Olá, meu nome é Fabio
```

Mostre a resposta amigável e a rota social sem chamada de LLM.

### 2. Memória e limite

```text
Qual meu limite?
Aumenta para 15 mil
```

Mostre a memória LangGraph, o checkpoint e os botões HITL. Use **Não autorizar** para provar que a
operação é cancelada; repita e use **Autorizar** para mostrar `update_card_limit` via MCP.

### 3. Pix com HITL

```text
Faça um Pix de R$ 6.000 para a chave maria@example.com
```

No dashboard, acompanhe `Guardrails → Roteamento → RBAC → HITL → MCP → Resposta`.

### 4. RAG oficial

```text
Qual a tarifa de saque em conta corrente?
Me fale sobre o pacote essencial para conta corrente.
Quais são as taxas de investimentos e fundos?
Como funciona o consignado para aposentados do INSS?
```

Abra as evidências para mostrar fontes, retrieval, provider e contexto aprovado.

### 5. Guardrails

```text
Meu iToken é 123456, consulte meu saldo.
```

Mostre que a solicitação é bloqueada antes de planner, RAG ou MCP.

### 6. RBAC

Entre como gerente, consulte o cliente `456` e tente uma escrita. Leitura é permitida; escrita é
negada. Como cliente, o acesso a outra conta retorna orientação amigável e gera `ACCESS_DENIED`.

### 7. Emergência

```text
Fui roubado e preciso bloquear meu cartão.
```

Mostre a rota prioritária, mudança de estado e auditoria `CARD_BLOCKED`.

## Pitch em cinco frases

1. “A LLM entende e sintetiza, mas não controla segurança ou dinheiro.”
2. “O Harness nativo aplica guardrails, RBAC, políticas, HITL e auditoria.”
3. “O MCP é o gateway real entre o agente e os sistemas bancários simulados.”
4. “O RAG não busca na web durante o atendimento e não inventa valores ausentes.”
5. “O dashboard mostra a jornada completa sem expor chain-of-thought.”

## Preparação antes da gravação

```powershell
docker compose up --build -d
docker compose ps
```

- confirme que os cinco serviços estão saudáveis;
- deixe chat e dashboard lado a lado;
- use uma sessão nova para a narrativa principal;
- explique que a auditoria persiste entre reinícios;
- mantenha `.temp/06_project_pitch.md` aberto como roteiro pessoal detalhado.

## Demonstrar o fallback Gemma

O Gemma é usado na síntese documental, não em saldo, Pix, limite, saudações ou guardrails. Para uma
demonstração previsível sem alterar código, configure temporariamente na `.env`:

```dotenv
LLM_GROUNDED_FAQ_ENABLED=true
LLM_PROVIDER=docker_model_runner
LLM_FALLBACK_PROVIDER=local
DOCKER_MODEL_RUNNER_MODEL=gemma4:latest
COMPOSE_DOCKER_MODEL_RUNNER_BASE_URL=http://host.docker.internal:12434/engines/v1
```

Recrie `api` e `mcp-server`, faça uma pergunta sobre tarifas e mostre no dashboard o provider
`docker-model-runner` e o modelo `gemma4:latest`. Depois restaure `LLM_PROVIDER=openai` e
`LLM_FALLBACK_PROVIDER=docker_model_runner`.
