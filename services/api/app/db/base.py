# File purpose: Manages base database lifecycle and session infrastructure.
# Main declarations: Base defines base state or behavior.

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
