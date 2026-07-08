from app.schemas.base import ApiModel
from app.schemas.user import User


class LoginInput(ApiModel):
    email: str
    password: str


class AuthResult(ApiModel):
    access_token: str
    user: User

