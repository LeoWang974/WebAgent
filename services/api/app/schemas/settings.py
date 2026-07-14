from app.schemas.base import ApiModel


class DataContextSettings(ApiModel):
    auto_summarize_context: bool
    context_retention_days: int
    max_context_messages: int
    save_conversation_history: bool
    save_uploaded_files: bool


class ProfileUpdate(ApiModel):
    avatar_url: str | None = None
    email: str
    nickname: str


class PasswordUpdate(ApiModel):
    current_password: str
    new_password: str
