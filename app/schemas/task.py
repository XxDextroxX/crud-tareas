import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Prioridad(str, Enum):
    baja = "baja"
    media = "media"
    alta = "alta"


class Estado(str, Enum):
    pendiente = "pendiente"
    en_progreso = "en_progreso"
    completada = "completada"


class TaskBase(BaseModel):
    nombre: str
    descripcion: str | None = None
    fecha_limite: datetime | None = None
    prioridad: Prioridad = Prioridad.media
    estado: Estado = Estado.pendiente
    nota: str | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    nombre: str | None = None
    descripcion: str | None = None
    fecha_limite: datetime | None = None
    prioridad: Prioridad | None = None
    estado: Estado | None = None
    nota: str | None = None


class TaskResponse(TaskBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
