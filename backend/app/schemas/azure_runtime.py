from pydantic import BaseModel, Field


class AzureRuntimeConfigPayload(BaseModel):
    """Corpo opcional para PUT — omitir campo = manter valor actual (env ou base)."""

    azure_ai_project_endpoint: str | None = Field(None, description="URL do projecto Foundry / AI Services")
    azure_ai_project_connection_string: str | None = Field(None, description="Connection string alternativa ao endpoint")
    azure_ai_agent_id: str | None = None
    azure_tenant_id: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None


class AzureRuntimeConfigResponse(BaseModel):
    azure_ai_project_endpoint_masked: str = ""
    azure_ai_project_connection_string_set: bool = False
    azure_ai_agent_id_masked: str = ""
    azure_tenant_id_set: bool = False
    azure_client_id_set: bool = False
    azure_client_secret_set: bool = False
    ready_for_agents: bool = False


class AzureRuntimeTestResponse(BaseModel):
    """Resultado agregado do teste de ligação (Agents e/ou OpenAI REST)."""

    ok: bool
    message: str
    agents_ok: bool | None = None
    agents_detail: str | None = None
    openai_ok: bool | None = None
    openai_detail: str | None = None


class AzureAiRequestProbeResponse(BaseModel):
    """Teste com requisições reais: POST chat/completions (OpenAI) e turno mínimo (Agents)."""

    ok: bool
    message: str
    openai_request_ok: bool
    openai_request_detail: str
    agents_request_ok: bool
    agents_request_detail: str
