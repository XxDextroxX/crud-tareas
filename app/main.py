from fastapi import FastAPI

import app.models  # noqa: F401 — registra todos los modelos con SQLAlchemy
from app.auth.router import router as auth_router
from app.routers.tasks import router as tasks_router
from app.routers.users import router as users_router

app = FastAPI(
    title="Todo API",
    description="CRUD de tareas con FastAPI y PostgreSQL",
    version="1.0.0",
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(tasks_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
