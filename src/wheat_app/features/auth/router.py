# src/wheat_app/features/auth/router.py
"""Auth: 路由"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "auth", "status": "ok"}
