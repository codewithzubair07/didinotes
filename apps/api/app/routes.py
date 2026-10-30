from fastapi import APIRouter, Request

from app.config_loader import TaskType

DEMO_BANNER = "Demo. Do not enter real patient data."

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "banner": DEMO_BANNER}


@router.get("/config/task-types")
def task_types(request: Request) -> list[TaskType]:
    return request.app.state.task_types
