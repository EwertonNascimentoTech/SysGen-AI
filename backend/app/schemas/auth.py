from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MeResponse(BaseModel):
    id: int
    email: str
    full_name: str
    roles: list[str]
    has_github: bool = False
    """True se existe identidade OAuth GitHub ligada (token para API)."""

    class Config:
        from_attributes = True
