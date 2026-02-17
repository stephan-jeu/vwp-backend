from __future__ import annotations

from typing import Sequence, Any
from enum import Enum

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserBase
from app.services.soft_delete import soft_delete_entity


def _enum_to_value(value: Any, enum_cls: type[Enum]) -> Any:
    """Return enum's value string for DB if input is an enum or a member name string.

    Args:
        value: Incoming value (may be Enum, string of member name, actual value, or None).
        enum_cls: The Enum class to coerce against.

    Returns:
        The enum's value (e.g., 'Intern') or the original value if not applicable.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, str):
        # Try matching by member name (e.g., 'INTERN' -> ContractType.INTERN.value)
        try:
            return enum_cls[value].value  # type: ignore[index]
        except KeyError:
            return value


async def list_users_full(db: AsyncSession, q: str | None = None) -> list[User]:
    """List users optionally filtered by name.

    Args:
        db: Async SQLAlchemy session.
        q: Optional case-insensitive substring to match against full_name and email.

    Returns:
        List of User rows ordered by full_name.
    """
    stmt: Select[tuple[User]] = select(User).order_by(User.full_name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((User.full_name.ilike(like)) | (User.email.ilike(like)))
    rows: Sequence[User] = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    """Create a new user.

    Args:
        db: Async SQLAlchemy session.
        payload: UserCreate data.

    Returns:
        The persisted User instance.
    """
    # Serialize and defensively coerce enums to their DB labels
    data = payload.model_dump(mode="json")
    
    # Validation: Check if email already exists
    existing = await db.execute(
        select(User).where(User.email == data["email"], User.deleted_at == None)
    )
    if existing.scalar_one_or_none():
         raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email_already_exists"
        )

    data["contract"] = _enum_to_value(data.get("contract"), UserBase.ContractType)
    data["experience_bat"] = _enum_to_value(
        data.get("experience_bat"), UserBase.ExperienceBat
    )

    user = User(**data)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email_already_exists"
        )
    await db.refresh(user)

    return user


async def update_user(db: AsyncSession, user_id: int, payload: UserUpdate) -> User:
    """Update an existing user with partial fields.

    Args:
        db: Async SQLAlchemy session.
        user_id: Target user id.
        payload: Fields to update.

    Returns:
        Updated User.
    """
    row = await db.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Serialize enums to their values and only include provided fields
    data = payload.model_dump(mode="json", exclude_unset=True)

    # Validation: Check if email already exists (if changing)
    if "email" in data and data["email"] != row.email:
        existing = await db.execute(
            select(User).where(User.email == data["email"], User.deleted_at == None)
        )
        if existing.scalar_one_or_none():
             raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="email_already_exists"
            )

    if "contract" in data:
        data["contract"] = _enum_to_value(data.get("contract"), UserBase.ContractType)
    if "experience_bat" in data:
        data["experience_bat"] = _enum_to_value(
            data.get("experience_bat"), UserBase.ExperienceBat
        )
    for k, v in data.items():
        setattr(row, k, v)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email_already_exists"
        )

    await db.refresh(row)
    return row


async def delete_user(db: AsyncSession, user_id: int) -> None:
    """Delete a user by id.

    Args:
        db: Async SQLAlchemy session.
        user_id: Target user id.

    Returns:
        None. Raises 404 if not found.
    """
    row = await db.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await soft_delete_entity(db, row, cascade=True)
    await db.commit()


async def get_user_by_reset_token(db: AsyncSession, token: str) -> User | None:
    """Find user by reset or activation token."""
    # We use the same field or logic? 
    # Model has `activation_token` and `reset_password_token`.
    # Let's check both for simplicity or separate methods?
    # Context suggests we might use one endpoint for both.
    
    # Check activation token first
    stmt = select(User).where(User.activation_token == token, User.deleted_at == None)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        return user
        
    # Check reset token
    # TODO: Check expiry
    stmt = select(User).where(User.reset_password_token == token, User.deleted_at == None)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def set_user_password(db: AsyncSession, user: User, password: str) -> None:
    from app.services.auth_service import get_password_hash
    
    user.hashed_password = get_password_hash(password)
    user.activation_token = None
    user.reset_password_token = None
    user.reset_password_token_expires_at = None
    
    await db.commit()
    await db.refresh(user)
