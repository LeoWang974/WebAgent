# File purpose: Defines Pydantic API contracts for settings.
# Main declarations: DataContextSettings defines data context settings state or behavior;
# InterfaceSettings defines interface settings state or behavior; ProfileUpdate defines profile
# update state or behavior; PasswordUpdate defines password update state or behavior.

from app.schemas.base import ApiModel


class DataContextSettings(ApiModel):
    auto_summarize_context: bool
    context_retention_days: int
    max_context_messages: int
    save_conversation_history: bool
    save_uploaded_files: bool


class InterfaceSettings(ApiModel):
    developer_mode: bool = False


class ProfileUpdate(ApiModel):
    avatar_url: str | None = None
    email: str
    nickname: str
    username: str | None = None


class PasswordUpdate(ApiModel):
    current_password: str
    new_password: str
    relogin: bool = False
