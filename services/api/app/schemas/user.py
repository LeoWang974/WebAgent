# File purpose: Defines Pydantic API contracts for user.
# Main declarations: User defines user state or behavior; AdminUser defines admin user state or
# behavior; AdminPasswordReset defines admin password reset state or behavior.

from app.schemas.base import ApiModel


class User(ApiModel):
    id: str
    nickname: str
    email: str
    username: str | None = None
    avatar_url: str | None = None
    role: str = "user"


class AdminUser(User):
    conversation_count: int = 0
    created_at: str | None = None
    password_mask: str = "********"
    updated_at: str | None = None


class AdminPasswordReset(ApiModel):
    new_password: str
