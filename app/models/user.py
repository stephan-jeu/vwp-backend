from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class User(TimestampMixin, Base):
    """User entity representing an application user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)

    class ContractType(StrEnum):
        INTERN = "Intern"
        FLEX = "Flex"
        ZZP = "ZZP"

    class ExperienceBat(StrEnum):
        NIEUW = "Nieuw"
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
    smp: Mapped[bool] = mapped_column(default=False, server_default="false")
    pad: Mapped[bool] = mapped_column(default=False, server_default="false")
    langoor: Mapped[bool] = mapped_column(default=False, server_default="false")
    roofvogel: Mapped[bool] = mapped_column(default=False, server_default="false")
    wbc: Mapped[bool] = mapped_column(default=False, server_default="false")
    fiets: Mapped[bool] = mapped_column(default=False, server_default="false")
    hup: Mapped[bool] = mapped_column(default=False, server_default="false")
    dvp: Mapped[bool] = mapped_column(default=False, server_default="false")
    vleermuis: Mapped[bool] = mapped_column(default=False, server_default="false")
    zwaluw: Mapped[bool] = mapped_column(default=False, server_default="false")
    vlinder: Mapped[bool] = mapped_column(default=False, server_default="false")
    zangvogel: Mapped[bool] = mapped_column(default=False, server_default="false")
    biggenkruid: Mapped[bool] = mapped_column(default=False, server_default="false")
    schijfhoren: Mapped[bool] = mapped_column(default=False, server_default="false")
