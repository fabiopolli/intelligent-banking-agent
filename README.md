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
- Streamlit separado em chat do cliente e painel técnico do avaliador
- instrumentação opcional LangSmith para traces do Harness, nós, tools e RAG
- Docker e GitHub Actions básicos
- abstração de workflow graph preparada para futura integração com LangGraph real
- `LangGraph` instalado na venv e `StateGraph` ativo em runtime
- trilha de auditoria append-only para `PIX`, `LIMIT_CHANGE` e `CARD_BLOCKED`
- RAG local com ingestao real do PDF de tarifas, snapshots oficiais de atendimento/politicas, cache runtime, reranking local e grounding sources
- respostas documentais de tarifa com fallback seguro, copy de atendimento ao cliente e primeira sintese grounded para `Saque conta corrente`
- RAG refatorado em `app/services/knowledge/` com modulos separados para config, schemas, ingestao, retrieval, reranking, tokenizacao, service e sintese
- GitHub Actions verde apos estabilizacao dos testes de RAG em ambiente sem cache runtime

## Estratégia de Entrega

O projeto é desenvolvido por slices verticais.

Cada slice deve evoluir:

1. backend do caso de uso
2. frontend mínimo para validar o caso
3. QA do slice
4. atualização de checklist
5. atualização incremental deste README
6. commit(s) do slice

O workflow agora exige ativacao explicita de persona para trabalho significativo. Em um slice normal, Codex deve conduzir automaticamente Tech Lead, Architect quando necessario, QA/QE, Backend, Frontend, QA/QE novamente, Technical Writer e Tech Lead review, parando apenas em gates humanos ou ambiguidades bloqueantes.

## Como Rodar Localmente

### Passo a passo recomendado

1. inicie o backend em um terminal
2. mantenha esse terminal aberto
3. inicie o chat do cliente em outro terminal
4. opcionalmente inicie o painel técnico em um terceiro terminal
5. abra os Streamlits lado a lado para validar chat, estado, trace e auditoria

### Backend

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Quando estiver saudável, o backend deve ficar disponível em:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`

### Chat do Cliente

```powershell
.\.venv\Scripts\python -m streamlit run frontend/customer_chat.py --server.address 127.0.0.1 --server.port 8501
```

Quando estiver saudável, o chat deve ficar disponível em:

- `http://127.0.0.1:8501`

### Painel Técnico

```powershell
.\.venv\Scripts\python -m streamlit run frontend/ops_dashboard.py --server.address 127.0.0.1 --server.port 8502
```

Quando estiver saudável, o painel deve ficar disponível em:

- `http://127.0.0.1:8502`

No painel técnico, valide:

- `Customer State` para saldo, limite, segmento e status do cartão
- `Harness Trace` para rota, latência, HITL e fontes
- `Knowledge Base` para contagem de documentos ingeridos e status do PDF
- `RAG Evidence` para fontes oficiais retornadas pelo RAG
- `Critical Audit` para eventos append-only de `PIX`, `LIMIT_CHANGE` e `CARD_BLOCKED`

### Testes

```powershell
.\.venv\Scripts\python -m pytest -q
```

Resultado validado em 18 de julho de 2026:

- `18 passed, 1 warning`

### Observabilidade LangSmith

O projeto roda sem credenciais externas. Para enviar traces ao LangSmith, configure as variáveis antes de iniciar a API:

```powershell
$env:LANGSMITH_TRACING="true"
$env:LANGSMITH_API_KEY="<sua-chave>"
$env:LANGSMITH_PROJECT="itau-intelligent-banking-agent"
```

O painel técnico mostra o status em `Observability`.

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

- o chat do cliente fica separado do painel técnico
- o último trace do Harness pode ser consultado pelo painel via `/v1/mcp/trace/{session_id}`
- spans LangSmith opcionais instrumentam Harness, roteamento, nós, PIX, HITL e RAG
- checkpoints de confirmação aparecem como estado pendente
- a trilha de auditoria crítica pode ser inspecionada sem sair da demo
- o painel técnico usa refresh manual para reduzir ruído durante a apresentação

### FAQ Fast Path

- resposta grounded para perguntas documentais simples
- PDF local de tarifas ingerido em chunks com cache em `.runtime/knowledge_tariff_chunks.json`
- respostas de tarifa usam answer builder controlado com texto de atendimento ao cliente, sem despejar tabelas cruas do PDF
- follow-ups curtos de tarifa, como "Saque!", continuam no fluxo controlado de tarifas
- follow-ups com contexto, como "Saque conta corrente", nao repetem a mesma pergunta de contexto
- saque em conta corrente usa sintese grounded a partir da evidencia oficial recuperada do PDF
- o resumo oficial do PDF de tarifas permanece carregado mesmo com ingestao completa, estabilizando o RAG em CI sem cache runtime
- RAG organizado em modulos coesos em `app/services/knowledge/` para fontes, ingestao, retrieval, reranking, tokenizacao, schemas e sintese
- fontes retornadas em `grounding_sources` no payload do Harness
- frontend mostra a quantidade e a lista de fontes oficiais retornadas
- falha segura quando nao ha contexto oficial suficiente

## Próximos Passos

- `SLICE-LLM-GROUNDED-FAQ`: primeira integracao real com LLM, limitada a respostas documentais de FAQ/RAG
- manter Harness, RBAC, retrieval, source filtering, fallback e envelope de resposta fora da LLM
- enviar para a LLM apenas contexto aprovado de fontes oficiais recuperadas
- safe-fail quando nao houver contexto oficial suficiente, sem improvisar tarifa, regra ou valor
- expor no painel tecnico retrieval, contexto enviado, resposta sintetizada, guardrail/fallback e fontes
- depois da LLM documental, expandir multi-turno de RAG para servico, tipo de conta, pacote e canal
- depois disso, evoluir PIX para fluxo realista com chave, destinatario, confirmacao sensivel e autenticacao simulada por app
- consolidar README final, evidencias de teste, Tech Lead review e PR para `main`
