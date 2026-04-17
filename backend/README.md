# Backend (FastAPI)

Recomenda-se **Python 3.12+** (imagem Docker oficial); em 3.9 alguns módulos podem falhar ao importar devido a anotações `|` em SQLAlchemy.

## Azure AI

O chat PRD usa **Azure AI Agents** quando `AZURE_AI_PROJECT_ENDPOINT` (ou `AZURE_AI_PROJECT_CONNECTION_STRING`) e `AZURE_AI_AGENT_ID` estão definidos; caso contrário usa-se **Azure OpenAI** via REST (`AZURE_OPENAI_*`). Credenciais: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` e `AZURE_CLIENT_SECRET` para aplicação no Entra ID, ou `DefaultAzureCredential` (ex.: `az login` em desenvolvimento).

Variáveis documentadas em `backend/.env.example` e na raiz `.env.example`. Configuração opcional persistida na API `GET/PUT /api/settings/azure-runtime`.

**Teste de ligação** (sem custo de modelo: Agents `get_agent`; OpenAI `GET /openai/deployments`): `POST /api/settings/azure-runtime/test` — UI: «Testar ligação (metadados)». CLI: `PYTHONPATH=. python scripts/test_azure_agent.py`.

**Teste de requisição** (POST real: OpenAI `chat/completions` + turno mínimo Agents — pode gerar custo de tokens): `POST /api/settings/azure-runtime/request-probe` — UI: «Testar requisição ao modelo». CLI: `PYTHONPATH=. python scripts/test_azure_ai_request.py` ou `docker compose run --rm backend python scripts/test_azure_ai_request.py` (com `compose.env` preenchido).
