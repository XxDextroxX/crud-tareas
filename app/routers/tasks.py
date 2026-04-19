import math
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ──────────────────────────── list (con filtros y paginación) ────────────────────────────

@router.get("/")
async def list_tasks(
    # Paginación
    page: int = Query(default=1, ge=1, description="Número de página"),
    limit: int = Query(default=20, ge=1, le=100, description="Resultados por página"),
    # Búsqueda
    q: str | None = Query(default=None, description="Buscar por nombre de tarea"),
    # Filtros de fecha
    fecha: date | None = Query(default=None, description="Fecha límite exacta (YYYY-MM-DD)"),
    fecha_inicio: date | None = Query(default=None, description="Inicio de rango de fecha (YYYY-MM-DD)"),
    fecha_fin: date | None = Query(default=None, description="Fin de rango de fecha (YYYY-MM-DD)"),
    # Filtros de estado y prioridad
    prioridad: str | None = Query(default=None, pattern="^(baja|media|alta)$"),
    estado: str | None = Query(default=None, pattern="^(pendiente|en_progreso|completada)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(Task).where(Task.user_id == current_user.id)

    if q:
        base = base.where(Task.nombre.ilike(f"%{q}%"))

    if fecha:
        # Convertir date a rango del día completo con timezone
        inicio_dia = datetime(fecha.year, fecha.month, fecha.day, tzinfo=timezone.utc)
        fin_dia = datetime(fecha.year, fecha.month, fecha.day, 23, 59, 59, tzinfo=timezone.utc)
        base = base.where(Task.fecha_limite.between(inicio_dia, fin_dia))
    elif fecha_inicio or fecha_fin:
        if fecha_inicio:
            base = base.where(Task.fecha_limite >= datetime(fecha_inicio.year, fecha_inicio.month, fecha_inicio.day, tzinfo=timezone.utc))
        if fecha_fin:
            base = base.where(Task.fecha_limite <= datetime(fecha_fin.year, fecha_fin.month, fecha_fin.day, 23, 59, 59, tzinfo=timezone.utc))

    if prioridad:
        base = base.where(Task.prioridad == prioridad)

    if estado:
        base = base.where(Task.estado == estado)

    # Total de resultados para el paginado
    count_query = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    skip = (page - 1) * limit
    items_query = base.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    items_result = await db.execute(items_query)
    items = items_result.scalars().all()

    return {
        "items": [TaskResponse.model_validate(t) for t in items],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if total > 0 else 1,
    }


# ──────────────────────────── create ────────────────────────────

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = Task(**data.model_dump(), id=uuid.uuid4(), user_id=current_user.id)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


# ──────────────────────────── get one ────────────────────────────

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return task


# ──────────────────────────── update ────────────────────────────

@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    await db.flush()
    await db.refresh(task)
    return task


# ──────────────────────────── delete ────────────────────────────

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    await db.delete(task)
