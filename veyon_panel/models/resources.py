from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from veyon_panel.db.base import Base


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    icon: Mapped[str] = mapped_column(String(32), default="room")
    color: Mapped[str] = mapped_column(String(16), default="#4d78d0")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    computers: Mapped[list["Computer"]] = relationship(
        back_populates="environment", passive_deletes=True
    )


class Computer(Base):
    __tablename__ = "computers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    host: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    environment_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    api_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auth_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    environment: Mapped[Environment | None] = relationship(back_populates="computers")

    @property
    def has_credentials(self) -> bool:
        return bool(self.credentials_encrypted)


class Software(Base):
    __tablename__ = "softwares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    url_local: Mapped[str] = mapped_column(String(2000))
    url_publica: Mapped[str] = mapped_column(String(2000))
    argumentos_instalacao: Mapped[str] = mapped_column(String(1000), default="/quiet /norestart")


class RepositoryScript(Base):
    __tablename__ = "repositorio_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), index=True)
    nome_arquivo: Mapped[str] = mapped_column(String(255))
    data_upload: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    tipo: Mapped[str] = mapped_column(String(8))
