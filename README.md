# Intelligent Banking Agent

Demo local de um agente bancário inteligente com FastAPI, fluxo de atendimento stateful e evolução orientada a slices verticais.

## Status Atual

Em 18 de julho de 2026, o projeto já possui:

- backend FastAPI inicial
- mocks internos stateful
- harness com RBAC e guardrails
- fluxo de PIX com HITL para alto valor
- coleta multi-turno de valor e chave Pix antes de executar ou pausar a transacao
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
- catalogo curado e versionado por produto em `knowledge/catalog/products.json`, com PostgreSQL/pgvector no caminho Docker
- respostas documentais de tarifa com fallback seguro, copy de atendimento ao cliente e sintese LLM grounded quando um provider estiver habilitado
- RAG refatorado em `app/services/knowledge/` com modulos separados para config, schemas, ingestao, retrieval, reranking, tokenizacao, service e sintese
- provider OpenAI opcional para FAQ/RAG grounded via Responses API, desligado por padrao e com fallback local deterministico
- provider Docker Model Runner opcional para FAQ/RAG grounded via API OpenAI-compatible local, desligado por padrao e com fallback local deterministico
- MCP-style internal tool boundary protegido por `X-Internal-Tool-Key`, com registry de tools e resources oficiais
- servidor MCP real separado em `app.mcp.server`, expondo resources oficiais e tools seguras para agentes sem bypass de Harness/RBAC/HITL/auditoria
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
- `29 passed, 2 warnings` apos MCP real, Docker Model Runner provider e correcao visual Streamlit
- `30 passed, 2 warnings` apos smoke MCP Streamable HTTP com cliente MCP real e reforco visual dark-mode dos Streamlits
- `32 passed, 2 warnings` apos coleta multi-turno de valor/chave Pix e confirmacao visual com valor/chave no Streamlit
- `35 passed, 2 warnings` apos preflight Pix com limite diario, alerta de chave suspeita e bloqueio de credenciais sensiveis no chat
- `38 passed, 2 warnings` apos aumento de limite multi-turno com consulta de perfil, elegibilidade, confirmacao HITL, checkpoint e auditoria
- `39 passed, 2 warnings` apos polimento de chat RAG/LLM para tarifas, sem fontes visiveis no chat do cliente e com fallback controlado quando provider LLM falha
- `48 passed, 2 warnings` apos catalogo curado por produto, embedding deterministico, resposta grounded de consignado INSS, adapter PostgreSQL/pgvector e correcao do timeout de fallback
- `59 passed, 2 warnings` localmente e no container apos persistencia completa de chunks/fontes, respostas objetivas, isolamento de testes e failover OpenAI -> Gemma configuravel
- `79 passed, 2 warnings` localmente e no container apos reconciliacao integral das 25 paginas do PDF, catalogo estruturado completo, correcao do header de autenticacao e encerramento conversacional do chat
- Docker local validado com `docker build`, `docker compose up --build -d`, smoke HTTP da API/chat/painel/MCP, KB com `pdf_ingested=true`, cliente MCP Streamable HTTP real e `pytest` dentro do container API (`30 passed, 2 warnings`)

### Docker Compose

```powershell
docker compose up --build
```

Servicos previstos:

- PostgreSQL/pgvector: persistencia da KB em `127.0.0.1:5432` para uso local e inspecao pelo DBeaver
- API: `http://localhost:8000`
- Chat do cliente: `http://localhost:8501`
- Painel tecnico: `http://localhost:8502`
- MCP server: `http://localhost:8600/mcp`

O Compose sobe API, chat e painel tecnico. Os Streamlits usam `DEFAULT_API_URL=http://api:8000/v1` dentro da rede Docker. Se usar uma chave interna diferente da demo, configure:

```powershell
$env:INTERNAL_TOOL_API_KEY="<chave-interna>"
```

O chat inicia com um login simulado controlado para cliente, gerente ou administrador. Os tokens vêm
de `DEMO_CUSTOMER_TOKEN`, `DEMO_MANAGER_TOKEN` e `DEMO_ADMIN_TOKEN`, são validados pela API e nunca
aparecem na interface. A API deriva `principal_id`, cliente próprio, papel e scopes exclusivamente do
token; o campo `role` do body não concede autoridade. Se o chat retornar `403`, recrie API e chat
juntos para que ambos recebam o mesmo `.env`: `docker compose up -d --force-recreate api customer-chat`.

Na demo, o cliente `123` acessa somente a própria conta, o gerente possui leitura de clientes e o
administrador possui leitura e operações. Expressões explícitas como `cliente 456` são resolvidas em
código nativo antes do planner; o Harness aplica RBAC antes de dados e tools. Em produção, esse
registro local deve ser substituído por OIDC/OAuth2 Authorization Code com PKCE e JWT validado no servidor.

O PDF oficial de tarifas em `.docs/tabela_geral_de_tarifas_pf_pdf.pdf` e versionado no repositorio e copiado para a imagem Docker. A imagem do desafio em `.docs/desafio.png` permanece fora do Git.

### Knowledge Base Curada

A fonte canônica da KB local e o catalogo versionado em `knowledge/catalog/products.json`. Cada registro
possui id estavel, produto, topico, publico, versao, data de revisao, fonte e limitacoes. No Compose,
a API persiste os fatos curados em `knowledge_facts`, suas evidencias em `fact_evidence`, as origens em
`knowledge_sources` e o conteudo narrativo fragmentado em `knowledge_chunks`. Tarifas, regras e pacotes
ficam normalizados em `tariff_entries`, `tariff_rules`, `tariff_entry_rules`, `service_packages` e
`package_items`; `knowledge_pages` e `knowledge_sections` preservam a proveniencia do PDF. A busca combina indice textual e
similaridade pgvector; nenhuma consulta web acontece durante o atendimento. Localmente e em CI, o mesmo
catalogo funciona sem banco com retrieval em memoria.

O catálogo da tabela PF vigente em 01/07/2026 foi reconciliado visualmente nas 25 páginas e possui:

- 169 registros de tarifa, percentual, isenção, fórmula ou valor negociado;
- 50 pacotes e 78 itens de composição dos pacotes detalhados nas páginas 3 e 5;
- 56 regras e observações;
- 165 tarifas publicadas e 4 registros mantidos como `review_required`.

Os quatro registros bloqueados representam duas contradições existentes no próprio PDF entre as
páginas físicas 17 e 20: avaliação de bem em garantia (`R$ 748,00` versus `R$ 709,00`) e cadastro de
financiamento (`R$ 1.149,00` versus `R$ 1.025,00`). O chat não escolhe arbitrariamente um valor nem
expõe a divergência interna ao cliente: informa apenas que não consegue confirmar a tarifa e orienta
um canal seguro de consulta. `knowledge/catalog/tariff_reconciliation.json` contabiliza
linhas canônicas, aliases, pacotes, itens e regras página a página.

O PDF de tarifas continua versionado como evidencia de origem e seus chunks, pagina e hash ficam
persistidos no banco. Fatos que exigem associacao precisa entre colunas, como servico, canal e valor,
sao curados em registros estruturados para evitar interpretacao incorreta do layout. Para adicionar conhecimento:

1. criar ou revisar um registro no catalogo;
2. manter uma afirmacao factual curta e uma fonte rastreavel;
3. registrar limitacoes para valores, taxas, vigencia e elegibilidade;
4. rodar `pytest` local;
5. reconstruir o Compose para validar seed, persistencia e retrieval PostgreSQL.

O caso obrigatorio de consignado INSS responde que nao existe taxa unica aplicavel a todos quando a
fonte recuperada nao sustenta esse numero, orienta a simulacao vigente e preserva a pagina oficial no
payload de grounding.

#### DBeaver

Com o Compose em execucao, crie uma conexao PostgreSQL com:

- Host: `127.0.0.1`
- Porta: `5432` (ou o valor de `POSTGRES_HOST_PORT`)
- Database: `itau_agent`
- Usuario: `itau`
- Senha: `itau`
- SSL: desabilitado para o ambiente local

As tabelas centrais sao `knowledge_sources`, `knowledge_chunks`, `knowledge_facts`, `fact_evidence`,
`tariff_entries`, `tariff_rules`, `tariff_entry_rules`, `service_packages`, `package_items`,
`knowledge_pages` e `knowledge_sections`. O volume
Docker `knowledge-data` preserva os dados entre restarts dos containers.

### Observabilidade LangSmith

O projeto roda sem credenciais externas. Para enviar traces ao LangSmith, configure as variáveis antes de iniciar a API:

```powershell
$env:LANGSMITH_TRACING="true"
$env:LANGSMITH_API_KEY="<sua-chave>"
$env:LANGSMITH_PROJECT="itau-intelligent-banking-agent"
```

O painel técnico mostra o status em `Observability`.

### Planner Agentic e FAQ/RAG com OpenAI

O runtime usa a Responses API em duas fronteiras separadas: um planner que seleciona exatamente uma
capability registrada por function calling e um sintetizador documental grounded. O modelo propoe;
o Agent Harness valida RBAC, politicas, dados, HITL e auditoria antes de executar qualquer efeito.

```env
LLM_GROUNDED_FAQ_ENABLED=true
LLM_PROVIDER=openai
LLM_FALLBACK_PROVIDER=docker_model_runner
LLM_MODEL=gpt-5.4
LLM_REASONING_EFFORT=low
AGENTIC_PLANNER_ENABLED=true
PROMPT_PROFILE=banking-v1
OPENAI_API_KEY=<configure somente no .env ignorado pelo Git>
```

Os prompts versionados ficam em `prompts/manifest.json` e `prompts/banking-v1/`. O trace registra
perfil, versao e hash do prompt, modelo, function tool selecionada, rota, fallback, tokens e duracao.
As instrucoes internas sao escritas em ingles para facilitar manutencao entre providers, mas o contrato
do sintetizador exige respostas naturais em portugues do Brasil. Saudacoes, apresentacoes, agradecimentos
e despedidas obvias usam `social_fast_path` nativo, sem planner, retrieval ou consumo de tokens.
Sem chave, quota ou provider, o router deterministico mantem a aplicacao utilizavel; esse fallback e
resiliencia, nao evidencia de uma execucao LLM bem-sucedida.

Em 20 de julho de 2026, a integracao real com `gpt-5.6-sol` selecionou
`get_customer_balance` via function calling, retornou `planner.fallback_used=false` e registrou
466 tokens. O Harness executou a consulta nativa somente depois da selecao do planner.

### FAQ/RAG com Docker Model Runner

Tambem e possivel usar um modelo local via Docker Model Runner, mantendo a mesma interface OpenAI-compatible:

```powershell
docker desktop enable model-runner --tcp 12434
docker model pull gemma4:latest
$env:LLM_GROUNDED_FAQ_ENABLED="true"
$env:LLM_PROVIDER="docker_model_runner"
$env:DOCKER_MODEL_RUNNER_BASE_URL="http://localhost:12434/engines/v1"
$env:DOCKER_MODEL_RUNNER_MODEL="gemma4:latest"
```

Para Docker Compose, o `docker-compose.yml` ja aponta containers para `http://host.docker.internal:12434/engines/v1` quando `LLM_PROVIDER=docker_model_runner`. Em Docker Desktop no Windows, esse endpoint e o caminho mais direto para o container acessar o Model Runner que esta rodando no host.

O Model Runner e opcional: o projeto continua subindo sem ele. `LLM_PROVIDER` escolhe o provider primario
e `LLM_FALLBACK_PROVIDER` habilita a cascata OpenAI -> Gemma -> sintetizador deterministico sem alterar
codigo. O planner volta ao roteador deterministico se a OpenAI falhar; o Gemma atua somente na sintese
documental e recebe contexto aprovado pelo Harness. Em producao, essa politica pode ser movida para um
gateway de LLM com timeout, circuit breaker e health check, mantendo a aplicacao ligada a um unico
endpoint OpenAI-compatible. A API local do Model Runner nao e autenticada e deve ficar restrita ao ambiente interno.

Modelos locais candidatos para benchmark posterior:

- `ai/qwen3:latest`
- `ai/gemma3:latest`
- `ai/gpt-oss:latest`

Esses modelos nao sao baixados automaticamente e nao fazem parte do `pytest`, Docker build ou CI. A
selecao do modelo default sera feita por uma golden set comum, medindo grounding, abstencao, prompt
leak, latencia, tokens, memoria e disco. LLM-as-judge sera uma avaliacao offline e opt-in; o runtime
continuara com um unico modelo configurado e fallback deterministico, sem cascata automatica entre
modelos pesados.

Evidencia local em 18 de julho de 2026: `docker model status` reportou `Docker Model Runner is running`, `docker model list` encontrou `ai/smollm2`, e o provider `docker_model_runner` respondeu sem fallback com `token_usage`.

### Fluxo Agentic Controlado

O planner recebe somente a mensagem corrente e uma allowlist de capabilities. Ele escolhe busca
oficial, saldo, limite, Pix ou protecao emergencial. A decisao segue para o Harness e para o LangGraph;
o modelo nunca recebe credenciais, endpoints internos ou autoridade para executar diretamente.

```text
mensagem -> guardrails -> planner OpenAI -> capability allowlist -> Harness/RBAC
         -> LangGraph -> tool/workflow -> HITL/audit -> resposta
```

O aumento de limite e o Pix demonstram coleta multi-turno e confirmacao. Se a LLM falhar, o mesmo
workflow continua pelo router deterministico e o dashboard identifica explicitamente o fallback.

Para tarifas, a ordem atual e:

1. Harness classifica a pergunta documental e resolve perguntas estaveis de navegacao por fast path, sem aguardar LLM.
2. Harness recupera e ranqueia contexto oficial aprovado.
3. Consultas numéricas, isenções, percentuais, fórmulas e pacotes usam o builder estruturado sem LLM; contradições `review_required` são bloqueadas.
4. Outras perguntas documentais podem usar a LLM para sintetizar contexto oficial aprovado, sem expor arquivos, URLs ou páginas ao cliente.
5. Se a LLM estiver desligada, ausente ou falhar, o fluxo documental mantém fallback controlado sem despejar tabela crua do PDF.
6. Em todos os casos, `grounding_sources`, prompt, contexto aprovado, provider/model, fallback e token usage permanecem disponiveis no payload tecnico e no painel do avaliador.

O chat usa um timeout maior que o budget do provider LLM. Assim, se o Model Runner ou o modelo
configurado estiver indisponivel, a API consegue concluir o fallback antes de o Streamlit abandonar
a requisicao. Alteracoes nesses budgets devem preservar essa ordem.

O payload tecnico separa `api_total_ms`, `harness_total_ms`, `routing_ms`, `retrieval_ms`,
`provider_ms`, `composition_ms` e `knowledge_total_ms`. O chat mede ainda o round-trip observado,
o overhead aproximado de rede/cliente e o tempo do rerun do Streamlit; o dashboard apresenta os
tempos do backend no trace sem fazer chamadas adicionais.

## MCP, Tools e Resources

O projeto expõe duas camadas para representar o item MCP do desafio sem permitir que a LLM execute operações diretamente:

1. REST interno protegido em `/v1/mcp/*`, usado pela demo local e pelo painel tecnico.
2. Servidor MCP real em `app.mcp.server`, publicado no Compose em `http://localhost:8600/mcp`.

O servidor MCP real publica `get_customer_profile`, `get_card_limit`, `update_card_limit` e
`create_pix`, alem das tools de knowledge e Harness. As duas tools de escrita apenas iniciam o
workflow controlado: elegibilidade, politica, confirmacao/HITL e auditoria continuam obrigatorias.

Nesta demo, os tools MCP-style usam REST interno como transporte local. Isso nao muda a arquitetura: MCP e o contrato de tools/resources para o agente; REST e apenas o adapter interno simples usado para executar e demonstrar essas tools localmente. Um servidor MCP real pode substituir esse adapter preservando o Harness, RBAC, HITL, auditoria e os nomes das tools.

Para rodar o servidor MCP real fora do Compose:

```powershell
.\.venv\Scripts\python -m app.mcp.server
```

O endpoint `http://localhost:8600/mcp` usa MCP Streamable HTTP. Um `GET` simples no navegador ou em `curl` pode retornar `406 Not Acceptable`, porque o servidor espera o protocolo MCP e headers de negociação do cliente, não uma rota REST comum. No Windows, prefira `127.0.0.1` no smoke para evitar ambiguidade de resolução de `localhost`. Para validar o servidor, use um cliente MCP:

```powershell
.\.venv\Scripts\python scripts\smoke_mcp_client.py --url http://127.0.0.1:8600/mcp
```

Saída esperada:

```json
{
  "tools": ["search_tariff_knowledge", "send_agent_message", "get_demo_status"],
  "resources": ["itau://mcp/tools", "itau://knowledge/resources"],
  "pdf_ingested": true
}
```

O mesmo smoke também roda no pytest e inicia um servidor MCP temporário em porta livre:

```powershell
.\.venv\Scripts\python -m pytest tests/test_smoke_backend.py::test_mcp_streamable_http_client_smoke -q
```

Tools expostas pelo servidor MCP real:

- `search_tariff_knowledge`: consulta RAG oficial com evidencias.
- `send_agent_message`: envia uma mensagem pelo Agent Harness, preservando RBAC, HITL, guardrails e auditoria.
- `get_demo_status`: retorna status de KB, observabilidade, tools e resources.

Resources expostos pelo servidor MCP real:

- `itau://mcp/tools`
- `itau://knowledge/resources`

Endpoints tecnicos protegidos:

- `GET /v1/mcp/tools`
- `GET /v1/mcp/resources`
- `GET /v1/mcp/users/profile/{customer_id}`
- `GET /v1/mcp/accounts/balance/{customer_id}`
- `POST /v1/mcp/cards/limit`
- `POST /v1/mcp/payments/pix`
- `GET /v1/mcp/audit/{customer_id}`
- `GET /v1/mcp/audit-integrity`
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
- coleta valor e chave Pix de destino antes de executar
- permite completar dados faltantes em turnos seguintes da mesma sessao
- aplica preflight de seguranca inspirado no Pix Itau: limite diario simulado, alerta de chave/atividade suspeita e bloqueio quando a conversa contem senha, iToken, CVV ou dados completos de cartao
- executa `PIX` abaixo do threshold diretamente
- exige confirmação para `PIX` de alto valor
- mostra valor e chave Pix na faixa de confirmação do chat antes de o cliente enviar `confirmo`
- rejeita `PIX` sem saldo suficiente, inclusive apos confirmação HITL
- persiste checkpoint local em `.runtime/checkpoints.json` até a confirmação
- atualiza saldo stateful após execução

### Cartões e Emergência

- consulta de limite
- aumento de limite multi-turno com consulta de perfil, politica de elegibilidade, confirmacao explicita e auditoria `LIMIT_CHANGE`
- bloqueio de aumento quando falta valor, quando o cartao nao esta ativo, quando o novo limite nao aumenta o atual ou quando excede a politica simulada
- bloqueio de cartão por emergência
- manutenção de estado do cartão no mock interno
- emissão de eventos de auditoria para operações críticas

### Observabilidade Local da Demo

- o chat do cliente fica separado do painel técnico
- o último trace e o histórico da sessão podem ser consultados pelo painel via `/v1/mcp/trace/{session_id}`
- PIX de alto valor preserva os eventos HITL `created`, `resumed` e `completed` com um único
  `correlation_id`, timestamps e duração do ciclo
- o dashboard identifica o componente como `LLM Planner`; confirmações HITL mostram
  `Not used this turn`, pois o Harness retoma o checkpoint diretamente sem nova classificação LLM
- spans LangSmith opcionais instrumentam Harness, roteamento, nós, PIX, HITL e RAG
- checkpoints de confirmação aparecem como estado pendente
- a trilha de auditoria crítica pode ser inspecionada sem sair da demo
- a métrica preserva o total de eventos persistidos, enquanto a lista mostra somente os três mais recentes
- o trace tecnico separa planner e compositor e mostra capability proposta, rota, prompt version/hash, contexto aprovado, tools chamadas, provider/model, fallback, token usage e tempo
- o painel técnico usa refresh manual para reduzir ruído durante a apresentação

### FAQ Fast Path

- resposta grounded para perguntas documentais simples
- catalogo curado por produto com ids, versao, publico, fonte, revisao e limitacoes
- PostgreSQL/pgvector no Compose e fallback local em memoria para testes reproduziveis
- caso de consignado INSS para aposentados e pensionistas com abstencao de taxa nao sustentada
- PDF local de tarifas ingerido em chunks com cache em `.runtime/knowledge_tariff_chunks.json`
- respostas de tarifa usam answer builder controlado com texto de atendimento ao cliente, sem despejar tabelas cruas do PDF
- perguntas sobre Serviços Essenciais usam a composição estruturada de `service_packages` e
  `package_items`, incluindo mensalidade e quantidades, sem cair em loop de esclarecimento
- respostas documentais terminam com um convite breve para o cliente continuar a conversa
- follow-ups curtos de tarifa, como "Saque!", continuam no fluxo controlado de tarifas
- follow-ups com contexto, como "Saque conta corrente", nao repetem a mesma pergunta de contexto
- tarifa, FAQ e politicas podem usar o provider LLM opcional quando ha fonte oficial recuperada
- tarifas sem LLM, sem contexto suficiente ou com falha de provider continuam no builder controlado para evitar invencao de valores ou despejo de tabela crua
- o resumo oficial do PDF de tarifas permanece carregado mesmo com ingestao completa, estabilizando o RAG em CI sem cache runtime
- RAG organizado em modulos coesos em `app/services/knowledge/` para fontes, ingestao, retrieval, reranking, tokenizacao, schemas e sintese
- fontes retornadas em `grounding_sources` no payload do Harness
- chat do cliente nao mostra fontes; painel tecnico mostra a quantidade e a lista de fontes oficiais retornadas
- falha segura quando nao ha contexto oficial suficiente

### Auditoria Critica

- no Docker Compose, toda acao critica e persistida em PostgreSQL na tabela append-only
  `critical_audit_events`; testes locais/CI usam o adapter em memoria para permanecerem deterministas
- `PIX`, `LIMIT_CHANGE` e `CARD_BLOCKED` ficam visiveis no painel tecnico
- eventos incluem ator e papel confiaveis, cliente-alvo, sessao/trace, acao, valor, status, motivo,
  payload redigido, timestamp, chave de idempotencia e hash encadeado
- o ciclo registra `requested`, `blocked`, `awaiting_hitl`, `confirmed`, `executed` e `failed` quando aplicavel
- trigger no banco rejeita `UPDATE` e `DELETE`; `GET /v1/mcp/audit-integrity` verifica a cadeia formada por
  `previous_hash` e `event_hash`
- reiniciar a API nao remove os eventos armazenados no volume PostgreSQL
- exportacao para armazenamento WORM/SIEM e uma evolucao de producao, nao uma capacidade implementada localmente

## Próximos Passos

O backend funcional ainda possui limites conhecidos: a configuracao de modelos precisa ser consolidada
antes de ser tratada como politica final. O login confiável local é apenas um adapter de demonstração, não um provedor de identidade de
produção. O histórico HITL de
PIX já é preservado em memória durante a sessão da API; persistência de traces após restart permanece
fora deste slice.

Ordem aprovada para concluir a entrega:

1. criar `main` a partir do commit-base `02bd31a`, mantendo `feat/tech-lead-planning` como origem do PR;
2. preservar no backend toda a passagem HITL de Pix: checkpoint, retomada e conclusao — concluído;
3. adicionar login simulado confiavel para cliente, gerente e administrador e provar RBAC para terceiros — concluído;
4. persistir auditoria critica append-only no PostgreSQL, com hash, idempotencia e bloqueio de alteracao/exclusao — concluído;
5. padronizar OpenAI `gpt-5.4` como primario, Gemma4 como fallback documental e resposta deterministica final;
6. mover prompts internos para ingles, exigir saida pt-BR e tratar saudacoes/apresentacoes antes do RAG;
7. medir separadamente latencia de frontend, API, roteamento, retrieval, provider e composicao;
8. aplicar o polimento final do frontend somente depois dos contratos de backend;
9. alinhar CI final, diagrama de arquitetura, evidencias, revisao Tech Lead e PR para `main`.

O planner nao usara Gemma4 como fallback: em falha da OpenAI ele retorna ao roteador deterministico.
Gemma4 fica restrito a sintese documental/conversacional aprovada. Identidade, RBAC, HITL, politicas,
execucao e auditoria permanecem sempre em codigo nativo no Agent Harness.
