# File purpose: Defines Pydantic API contracts for auth.
# Main declarations: LoginInput defines login input state or behavior; RegisterInput defines
# register input state or behavior; AuthResult defines auth result state or behavior;
# AdminUserCreate defines admin user create state or behavior.

from app.schemas.base import ApiModel
from app.schemas.user import User


class LoginInput(ApiModel):
    email: str | None = None
    username: str | None = None
    identifier: str | None = None
    password: str


class RegisterInput(LoginInput):
    email: str | None = None
    username: str | None = None
    nickname: str | None = None


class AuthResult(ApiModel):
    access_token: str
    user: User


class AdminUserCreate(ApiModel):
    email: str
    username: str | None = None
    nickname: str | None = None
    password: str
    role: str = "user"
