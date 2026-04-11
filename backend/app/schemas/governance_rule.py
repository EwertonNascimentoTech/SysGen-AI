from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.governance_catalog import RULE_KEYS, VIOLATION_MODES


class GovernanceRuleOut(BaseModel):
    id: int
    name: str
    description: str | None
    rule_key: str
    min_tags_value: int | None = None
    active: bool
    on_violation: Literal["bloqueio", "alerta"] = "bloqueio"

    class Config:
        from_attributes = True


class GovernanceRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    rule_key: str = Field(..., min_length=1, max_length=64)
    min_tags_value: int | None = Field(None, ge=1, le=50)
    active: bool = True
    on_violation: Literal["bloqueio", "alerta"] = "bloqueio"

    @model_validator(mode="after")
    def validate_rule_key(self):
        if self.rule_key not in RULE_KEYS:
            raise ValueError(f"rule_key inválido: use um de {sorted(RULE_KEYS)}")
        if self.rule_key == "min_tag_count":
            if self.min_tags_value is None:
                raise ValueError("Para min_tag_count informe min_tags_value >= 1")
        elif self.min_tags_value is not None:
            raise ValueError("min_tags_value só se aplica a rule_key min_tag_count")
        return self


class GovernanceRulePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None
    rule_key: str | None = Field(None, min_length=1, max_length=64)
    min_tags_value: int | None = None
    active: bool | None = None
    on_violation: Literal["bloqueio", "alerta"] | None = None

    @model_validator(mode="after")
    def validate_keys(self):
        if self.rule_key is not None and self.rule_key not in RULE_KEYS:
            raise ValueError(f"rule_key inválido: use um de {sorted(RULE_KEYS)}")
        if self.on_violation is not None and self.on_violation not in VIOLATION_MODES:
            raise ValueError("on_violation deve ser bloqueio ou alerta")
        return self
