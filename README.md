# Intelligent Banking Agent

Demo local de um agente bancário inteligente com FastAPI, fluxo de atendimento stateful e evolução orientada a slices verticais.

## Status Atual

Em 18 de julho de 2026, o projeto já possui:

- backend FastAPI inicial
- mocks internos stateful
- harness com RBAC e guardrails
- fluxo de PIX com HITL para alto valor
- fluxo de emergência com bloqueio de cartão
- frontend Streamlit inicial para validação local
- Docker e GitHub Actions básicos
- abstração de workflow graph preparada para futura integração com LangGraph real

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

### Backend

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
.\.venv\Scripts\python -m streamlit run frontend/streamlit_app.py
```

### Testes

```powershell
.\.venv\Scripts\python -m pytest -q
```

## Slices Já Visíveis na Demo

### PIX

- identifica fluxo de PIX
- executa `PIX` abaixo do threshold diretamente
- exige confirmação para `PIX` de alto valor
- atualiza saldo stateful após execução

### Cartões e Emergência

- consulta de limite
- bloqueio de cartão por emergência
- manutenção de estado do cartão no mock interno

### FAQ Fast Path

- resposta inicial estável para perguntas simples
- preparado para evolução posterior com RAG híbrido

## Próximos Passos

- integrar `StateGraph` real do LangGraph
- adicionar trilha de auditoria imutável
- implementar slice documental com RAG híbrido
- expandir frontend por slice
- consolidar documentação final para PR
