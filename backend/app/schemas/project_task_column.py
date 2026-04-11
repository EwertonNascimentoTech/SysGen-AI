from pydantic import BaseModel, Field


class ProjectTaskColumnOut(BaseModel):
    id: int
    project_id: int
    key: str
    title: str
    position: int
    color_hex: str
    is_done: bool

    class Config:
        from_attributes = True


class ProjectTaskColumnCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    color_hex: str | None = Field(None, max_length=7)
    key: str | None = Field(None, max_length=64, pattern=r"^[a-z0-9_]{1,64}$")
    is_done: bool = False


class ProjectTaskColumnPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=128)
    color_hex: str | None = Field(None, max_length=32)
    is_done: bool | None = None


class ProjectTaskColumnOrderBody(BaseModel):
    column_ids: list[int] = Field(min_length=1)
