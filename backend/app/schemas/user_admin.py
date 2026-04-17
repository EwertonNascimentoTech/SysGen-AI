from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=6)
    role_codes: list[str]
    github_login: str | None = Field(None, max_length=128)


class UserUpdate(BaseModel):
    """Campos opcionais; só os enviados no JSON são aplicados (PATCH)."""

    email: EmailStr | None = None
    full_name: str | None = Field(None, min_length=1, max_length=255)
    password: str | None = Field(None, min_length=6)
    role_codes: list[str] | None = None
    is_active: bool | None = None
    github_login: str | None = Field(None, max_length=128)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    roles: list[str]
    github_login: str | None = None

    class Config:
        from_attributes = True
