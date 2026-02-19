from __future__ import annotations

from typing import Annotated, TypeAlias

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.security import get_current_user, require_admin
from db.session import get_db

DbDep: TypeAlias = Annotated[AsyncSession, Depends(get_db)]
AdminDep: TypeAlias = Annotated[User, Depends(require_admin)]
UserDep: TypeAlias = Annotated[User, Depends(get_current_user)]
