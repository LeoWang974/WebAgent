from app.schemas.base import ApiModel
from app.schemas.user import User


class LoginInput(ApiModel):
    email: str
    password: str


class RegisterInput(LoginInput):
    nickname: str | None = None


class AuthResult(ApiModel):
    access_token: str
    user: User


class AdminUserCreate(ApiModel):
    email: str
    nickname: str | None = None
    password: str
    role: str = "user"
