from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, String, Index, text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin, SoftDeleteMixin


class User(TimestampMixin, SoftDeleteMixin, Base):
    """User entity representing an application user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Auth fields
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activation_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_password_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_password_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_users_email_unique_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
    admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    class ContractType(StrEnum):
        INTERN = "Intern"
        FLEX = "Flex"
        ZZP = "ZZP"

    class ExperienceBat(StrEnum):
        JUNIOR = "Junior"
        MEDIOR = "Medior"
        SENIOR = "Senior"

    contract: Mapped[ContractType | None] = mapped_column(
        Enum(
            ContractType,
            name="contract_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    experience_bat: Mapped[ExperienceBat | None] = mapped_column(
        Enum(
            ExperienceBat,
            name="experience_bat_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    smp_huismus: Mapped[bool] = mapped_column(default=False, server_default="false")
    smp_vleermuis: Mapped[bool] = mapped_column(default=False, server_default="false")
    smp_gierzwaluw: Mapped[bool] = mapped_column(default=False, server_default="false")
    pad: Mapped[bool] = mapped_column(default=False, server_default="false")
    langoor: Mapped[bool] = mapped_column(default=False, server_default="false")
    roofvogel: Mapped[bool] = mapped_column(default=False, server_default="false")
    wbc: Mapped[bool] = mapped_column(default=False, server_default="false")
    fiets: Mapped[bool] = mapped_column(default=False, server_default="false")
    vog: Mapped[bool] = mapped_column(default=False, server_default="false")
    hub: Mapped[bool] = mapped_column(default=False, server_default="false")
    dvp: Mapped[bool] = mapped_column(default=False, server_default="false")
    vrfg: Mapped[bool] = mapped_column(default=False, server_default="false")
    vleermuis: Mapped[bool] = mapped_column(default=False, server_default="false")
    zwaluw: Mapped[bool] = mapped_column(default=False, server_default="false")
    vlinder: Mapped[bool] = mapped_column(default=False, server_default="false")
    teunisbloempijlstaart: Mapped[bool] = mapped_column(
        default=False, server_default="false"
    )
    zangvogel: Mapped[bool] = mapped_column(default=False, server_default="false")
    biggenkruid: Mapped[bool] = mapped_column(default=False, server_default="false")
    schijfhoren: Mapped[bool] = mapped_column(default=False, server_default="false")

    class Language(StrEnum):
        EN = "EN"
        NL = "NL"

    language: Mapped[Language] = mapped_column(
        Enum(
            Language,
            name="language_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=Language.NL,
        server_default="NL",
        nullable=False,
    )
