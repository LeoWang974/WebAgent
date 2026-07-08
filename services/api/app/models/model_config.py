from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import IdMixin, TimestampMixin


class ModelConfig(IdMixin, TimestampMixin, Base):
    __tablename__ = "model_configs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    is_available: Mapped[bool] = mapped_column(default=True)

