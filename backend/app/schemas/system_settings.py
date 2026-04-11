from pydantic import BaseModel, Field


class GeneralSettingsOut(BaseModel):
    org_name: str
    locale: str
    audit_strict: bool
    ai_indexing: bool


class GeneralSettingsUpdate(BaseModel):
    org_name: str | None = Field(None, min_length=1, max_length=255)
    locale: str | None = Field(None, max_length=32)
    audit_strict: bool | None = None
    ai_indexing: bool | None = None
