from pydantic import BaseModel, Field

from app.services.column_rules import parse_rules


class ColumnRules(BaseModel):
    require_description: bool = False
    require_attachment_audit: bool = False
    require_po_assigned: bool = False
    require_github_tag: bool = False
    min_tag_count: int = Field(0, ge=0)


class ColumnOut(BaseModel):
    id: int
    title: str
    position: int
    color_hex: str
    rules: ColumnRules
    applied_rule_ids: list[int] = []

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_column(cls, col) -> "ColumnOut":
        d = parse_rules(col.rules_json)
        rules = ColumnRules(
            require_description=bool(d.get("require_description")),
            require_attachment_audit=bool(d.get("require_attachment_audit")),
            require_po_assigned=bool(d.get("require_po_assigned")),
            require_github_tag=bool(d.get("require_github_tag")),
            min_tag_count=int(d.get("min_tag_count") or 0),
        )
        ids = d.get("applied_rule_ids") or []
        if not isinstance(ids, list):
            ids = []
        clean_ids: list[int] = []
        for i in ids:
            try:
                clean_ids.append(int(i))
            except (TypeError, ValueError):
                pass
        return cls(
            id=col.id,
            title=col.title,
            position=col.position,
            color_hex=str(d.get("color_hex") or "#64748b"),
            rules=rules,
            applied_rule_ids=clean_ids,
        )


class TemplateOut(BaseModel):
    id: int
    name: str
    status: str
    version: int
    description: str | None = None
    methodology: str | None = None
    columns: list[ColumnOut] = []

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_template(cls, tpl) -> "TemplateOut":
        cols = sorted(tpl.columns, key=lambda c: c.position)
        return cls(
            id=tpl.id,
            name=tpl.name,
            status=tpl.status,
            version=tpl.version,
            description=getattr(tpl, "description", None),
            methodology=getattr(tpl, "methodology", None),
            columns=[ColumnOut.from_orm_column(c) for c in cols],
        )


class TemplateCreate(BaseModel):
    name: str
    column_titles: list[str]
    description: str | None = None
    methodology: str | None = None


class TemplatePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    methodology: str | None = None


class ColumnCreate(BaseModel):
    title: str
    color_hex: str | None = None
    rules: ColumnRules | None = None


class ColumnPatch(BaseModel):
    title: str | None = None
    color_hex: str | None = None
    rules: ColumnRules | None = None
    applied_rule_ids: list[int] | None = None


class ReorderColumnsBody(BaseModel):
    ordered_column_ids: list[int]


class DuplicateTemplateBody(BaseModel):
    name: str | None = None
