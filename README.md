# Intelligent Banking Agent

Demo local de um agente bancário inteligente com FastAPI, fluxo de atendimento stateful e evolução orientada a slices verticais.

## Status Atual

Em 18 de julho de 2026, o projeto já possui:

- backend FastAPI inicial
- mocks internos stateful
- harness com RBAC e guardrails
- fluxo de PIX com HITL para alto valor
- checkpoints HITL persistidos localmente para retomada de operacoes pendentes
- fluxo de emergência com bloqueio de cartão
- frontend Streamlit inicial para validação local
- painel de auditoria crítica e último resultado do agente no frontend
- shell Streamlit polido com chat, painéis de cliente, trace, evidências e auditoria
- Docker e GitHub Actions básicos
- abstração de workflow graph preparada para futura integração com LangGraph real
- `LangGraph` instalado na venv e `StateGraph` ativo em runtime
- trilha de auditoria append-only para `PIX`, `LIMIT_CHANGE` e `CARD_BLOCKED`
- RAG local inicial com recuperacao hibrida lexical/BM25-like e grounding sources

## Estratégia de Entrega

O projeto é desenvolvido por slices verticais.

Cada slice deve evoluir:

1. backend do caso de uso
2. frontend mínimo para validar o caso
3. QA do slice
4. atualização de checklist
5. atualização incremental deste README
6. commit(s) do slice

## Como Rodar Localmente

### Passo a passo recomendado

1. inicie o backend em um terminal
2. mantenha esse terminal aberto
3. inicie o frontend em outro terminal
4. abra a interface do Streamlit
5. valide snapshot, prompts e respostas do agente

### Backend

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Quando estiver saudável, o backend deve ficar disponível em:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`

### Frontend

```powershell
.\.venv\Scripts\python -m streamlit run frontend/streamlit_app.py
```

No frontend, confira se a sidebar está apontando para:

- `API URL = http://localhost:8000/v1`

Na tela da demo, valide também:

- `Customer` para saldo, limite, segmento e status do cartão
- `Agent Console` para chat e prompts rápidos por caso de uso
- `Harness Trace` para rota, latência, HITL e fontes
- `Evidence` para fontes oficiais retornadas pelo RAG
- `Critical Audit` para eventos append-only de `PIX`, `LIMIT_CHANGE` e `CARD_BLOCKED`

### Testes

```powershell
.\.venv\Scripts\python -m pytest -q
```

Resultado validado em 18 de julho de 2026:

- `13 passed, 1 warning`

### Troubleshooting rápido

Se o frontend mostrar erro como `WinError 10061`, normalmente significa que o backend não está rodando ou não está acessível na porta `8000`.

Checklist rápido:

1. confirmar se o terminal do backend continua aberto
2. confirmar se o backend subiu sem erro
3. abrir `http://127.0.0.1:8000/docs`
4. conferir a `API URL` no Streamlit

## Slices Já Visíveis na Demo

### PIX

- identifica fluxo de PIX
- executa `PIX` abaixo do threshold diretamente
- exige confirmação para `PIX` de alto valor
- rejeita `PIX` sem saldo suficiente, inclusive apos confirmação HITL
- persiste checkpoint local em `.runtime/checkpoints.json` até a confirmação
- atualiza saldo stateful após execução

### Cartões e Emergência

- consulta de limite
- bloqueio de cartão por emergência
- manutenção de estado do cartão no mock interno
- emissão de eventos de auditoria para operações críticas

### Observabilidade Local da Demo

- a última rota selecionada pelo Harness fica visível na interface
- a latência da chamada do agente aparece no painel `Harness Trace`
- checkpoints de confirmação aparecem como estado pendente
- a trilha de auditoria crítica pode ser inspecionada sem sair da demo
- snapshot e auditoria usam cache de sessão e refresh manual para reduzir reruns desnecessários

### FAQ Fast Path

- resposta grounded para perguntas documentais simples
- fontes retornadas em `grounding_sources` no payload do Harness
- frontend mostra a quantidade e a lista de fontes oficiais retornadas
- falha segura quando nao ha contexto oficial suficiente

## Próximos Passos

- ingerir o PDF de tarifas completo no pipeline documental
- adicionar resposta inteligente controlada com LLM usando apenas contexto aprovado pelo Harness
- consolidar documentação final para PR
