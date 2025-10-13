from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models import Base, TimestampMixin


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
        SENIOR = "Senior"
        GZ = "GZ"

    contract: Mapped[ContractType | None] = mapped_column(
        Enum(ContractType, name="contract_type"), nullable=True
    )
    experience_bat: Mapped[ExperienceBat | None] = mapped_column(
        Enum(ExperienceBat, name="experience_bat_type"), nullable=True
    )
    smp: Mapped[bool] = mapped_column(default=False, server_default="false")
    rugstreeppad: Mapped[bool] = mapped_column(default=False, server_default="false")
    huismus: Mapped[bool] = mapped_column(default=False, server_default="false")
    langoren: Mapped[bool] = mapped_column(default=False, server_default="false")
    roofvogels: Mapped[bool] = mapped_column(default=False, server_default="false")
    wbc: Mapped[bool] = mapped_column(default=False, server_default="false")
    fiets: Mapped[bool] = mapped_column(default=False, server_default="false")
    hup: Mapped[bool] = mapped_column(default=False, server_default="false")
    dvp: Mapped[bool] = mapped_column(default=False, server_default="false")
