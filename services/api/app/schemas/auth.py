from app.schemas.base import ApiModel
from app.schemas.user import User


class LoginInput(ApiModel):
    email: str | None = None
    username: str | None = None
    identifier: str | None = None
    password: str


class RegisterInput(LoginInput):
    email: str
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
