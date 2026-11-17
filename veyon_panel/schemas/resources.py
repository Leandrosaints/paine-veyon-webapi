from datetime import datetime

from pydantic import BaseModel, Field


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    icon: str = Field(default="room", max_length=32)
    color: str = Field(default="#4d78d0", max_length=16)


class EnvironmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    icon: str | None = Field(default=None, max_length=32)
    color: str | None = Field(default=None, max_length=16)
    sort_order: int | None = None


class EnvironmentRead(BaseModel):
    id: int
    name: str
    icon: str
    color: str
    sort_order: int
    created_at: datetime | None = None

    class Config:
        orm_mode = True


class ComputerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=253)
    environment_id: int | None = None
    api_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=500)


class ComputerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    host: str | None = Field(default=None, min_length=1, max_length=253)
    environment_id: int | None = None
    api_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class ComputerRead(BaseModel):
    id: int
    name: str
    host: str
    environment_id: int | None
    api_url: str | None
    notes: str | None
    has_credentials: bool = False
    sort_order: int
    created_at: datetime | None = None

    class Config:
        orm_mode = True

class ComputerCredentials(BaseModel):
    method: str = Field(min_length=1, max_length=64)
    credentials: dict
