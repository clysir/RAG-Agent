"""API 路由聚合 —— 在 main.py 里统一挂载。"""

from fastapi import APIRouter

from app.api import admin, auth, chat, health, memory, merchant, upload

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router)
api_router.include_router(upload.router)
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(merchant.router)
api_router.include_router(admin.router)
api_router.include_router(memory.router)
