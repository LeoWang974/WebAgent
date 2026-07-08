from sqlalchemy import ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import IdMixin, TimestampMixin


class UserSettings(IdMixin, TimestampMixin, Base):
    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    data_context: Mapped[dict] = mapped_column(JSON, default=dict)
    interface: Mapped[dict] = mapped_column(JSON, default=dict)

