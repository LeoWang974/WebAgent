from app.schemas.base import ApiModel


class User(ApiModel):
    id: str
    nickname: str
    email: str
    avatar_url: str | None = None
    role: str = "user"
