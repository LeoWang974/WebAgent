# File purpose: Implements the dependencies module for WebAgent.
# Main declarations: this file contains declarative configuration or re-exports and has no
# callable declarations.

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User
from app.services.persistence import get_current_user

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
