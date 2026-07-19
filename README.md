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
- provider OpenAI opcional para FAQ/RAG grounded via Responses API, desligado por padrao e com fallback local deterministico
- MCP-style internal tool boundary protegido por `X-Internal-Tool-Key`, com registry de tools e resources oficiais
- observabilidade de prompt, contexto aprovado, tools chamadas, provider/model, fallback, token usage e tempo no trace tecnico
- auditoria critica com `user`, `action`, `amount`, `timestamp` e hash encadeado append-only
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
- `Harness Trace` para rota, latência, HITL, fontes, tools chamadas, prompt/contexto LLM e token usage
- `Knowledge Base` para contagem de documentos ingeridos e status do PDF
- `RAG Evidence` para fontes oficiais retornadas pelo RAG
- `Critical Audit` para eventos append-only de `PIX`, `LIMIT_CHANGE` e `CARD_BLOCKED`

### Testes

```powershell
.\.venv\Scripts\python -m pytest -q
```

Resultado validado em 18 de julho de 2026:

- `27 passed, 2 warnings`
- Docker local validado com `docker build`, `docker compose up --build -d`, smoke HTTP da API/chat/painel, KB com `pdf_ingested=true` e `pytest` dentro do container API (`27 passed, 2 warnings`)

### Docker Compose

```powershell
docker compose up --build
```

Servicos previstos:

- API: `http://localhost:8000`
- Chat do cliente: `http://localhost:8501`
- Painel tecnico: `http://localhost:8502`

O Compose sobe API, chat e painel tecnico. Os Streamlits usam `DEFAULT_API_URL=http://api:8000/v1` dentro da rede Docker. Se usar uma chave interna diferente da demo, configure:

```powershell
$env:INTERNAL_TOOL_API_KEY="<chave-interna>"
```

O PDF oficial de tarifas em `.docs/tabela_geral_de_tarifas_pf_pdf.pdf` e versionado no repositorio e copiado para a imagem Docker. A imagem do desafio em `.docs/desafio.png` permanece fora do Git.

### Observabilidade LangSmith

O projeto roda sem credenciais externas. Para enviar traces ao LangSmith, configure as variáveis antes de iniciar a API:

```powershell
$env:LANGSMITH_TRACING="true"
$env:LANGSMITH_API_KEY="<sua-chave>"
$env:LANGSMITH_PROJECT="itau-intelligent-banking-agent"
```

O painel técnico mostra o status em `Observability`.

### FAQ/RAG com Sintese Opcional

O projeto permanece executavel sem credenciais externas. A primeira fronteira de LLM foi adicionada apenas para sintese documental grounded e fica desligada por padrao:

```powershell
$env:LLM_GROUNDED_FAQ_ENABLED="true"
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="<sua-chave>"
$env:LLM_MODEL="gpt-5.6-luna"
```

Sem `OPENAI_API_KEY`, ou se a chamada externa falhar, o sistema usa fallback local deterministico. A LLM nao recebe tools, estado bancario mutavel, permissoes, checkpoints ou autorizacao para side effects. Perguntas sem fonte oficial suficiente continuam em fallback seguro.

## MCP, Tools e Resources

O projeto expõe uma fronteira MCP-style para representar os sistemas internos do desafio sem permitir que a LLM execute operações diretamente.

Nesta demo, os tools MCP-style usam REST interno como transporte local. Isso nao muda a arquitetura: MCP e o contrato de tools/resources para o agente; REST e apenas o adapter interno simples usado para executar e demonstrar essas tools localmente. Um servidor MCP real pode substituir esse adapter preservando o Harness, RBAC, HITL, auditoria e os nomes das tools.

Endpoints tecnicos protegidos:

- `GET /v1/mcp/tools`
- `GET /v1/mcp/resources`
- `GET /v1/mcp/users/profile/{customer_id}`
- `GET /v1/mcp/accounts/balance/{customer_id}`
- `POST /v1/mcp/cards/limit`
- `POST /v1/mcp/payments/pix`
- `GET /v1/mcp/audit/{customer_id}`
- `GET /v1/mcp/trace/{session_id}`
- `GET /v1/mcp/knowledge/status`
- `GET /v1/mcp/observability/status`

Todos exigem header:

```text
X-Internal-Tool-Key: demo-internal-tool-key
```

Arquitetura intencional:

```text
LLM -> Harness -> RBAC / HITL / Audit / Guardrails -> MCP-style tool boundary -> mocks internos
```

O PDF de tarifas nao vira uma tool transacional. Ele e tratado como resource documental oficial (`itau://knowledge/tariff-pdf`) ingerido pelo RAG e exposto no registry MCP-style. Tools como `search_tariff_knowledge` consultam esse resource; tools como `create_pix` continuam passando por RBAC, HITL e auditoria.

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
- o trace tecnico mostra prompt, contexto aprovado, tools chamadas, provider/model, fallback, token usage e tempo quando o fluxo usa LLM/RAG
- o painel técnico usa refresh manual para reduzir ruído durante a apresentação

### FAQ Fast Path

- resposta grounded para perguntas documentais simples
- PDF local de tarifas ingerido em chunks com cache em `.runtime/knowledge_tariff_chunks.json`
- respostas de tarifa usam answer builder controlado com texto de atendimento ao cliente, sem despejar tabelas cruas do PDF
- follow-ups curtos de tarifa, como "Saque!", continuam no fluxo controlado de tarifas
- follow-ups com contexto, como "Saque conta corrente", nao repetem a mesma pergunta de contexto
- saque em conta corrente usa sintese grounded a partir da evidencia oficial recuperada do PDF
- FAQ e politicas podem usar o provider OpenAI opcional quando ha fonte oficial recuperada
- tarifas continuam no builder controlado para evitar invencao de valores ou despejo de tabela crua
- o resumo oficial do PDF de tarifas permanece carregado mesmo com ingestao completa, estabilizando o RAG em CI sem cache runtime
- RAG organizado em modulos coesos em `app/services/knowledge/` para fontes, ingestao, retrieval, reranking, tokenizacao, schemas e sintese
- fontes retornadas em `grounding_sources` no payload do Harness
- frontend mostra a quantidade e a lista de fontes oficiais retornadas
- falha segura quando nao ha contexto oficial suficiente

### Auditoria Critica

- toda acao critica gera evento append-only
- `PIX`, `LIMIT_CHANGE` e `CARD_BLOCKED` ficam visiveis no painel tecnico
- eventos incluem `user`, `action`, `amount`, `timestamp`, payload original e hash encadeado
- o hash encadeado (`previous_hash` e `event_hash`) demonstra imutabilidade sequencial para a demo

## Próximos Passos

- validar manualmente `SLICE-LLM-GROUNDED-FAQ` com `OPENAI_API_KEY` real, mantendo o mesmo contrato de contexto aprovado
- acompanhar GitHub Actions para confirmar `pytest` e `docker build`
- depois da LLM documental, expandir multi-turno de RAG para servico, tipo de conta, pacote e canal
- depois disso, evoluir PIX para fluxo realista com chave, destinatario, confirmacao sensivel e autenticacao simulada por app
- consolidar README final, evidencias de teste, Tech Lead review e PR para `main`
