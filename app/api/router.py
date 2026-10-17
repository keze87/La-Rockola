"""
Agregador de enrutadores HTTP de la API (/api/v1 y rutas raíz del frontend).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import commands, library, media, system

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(commands.router)
api_v1_router.include_router(library.router)
api_v1_router.include_router(media.router)
api_v1_router.include_router(system.router)

root_api_router = APIRouter(include_in_schema=False)
root_api_router.include_router(commands.router)
root_api_router.include_router(library.router)
root_api_router.include_router(media.router)
root_api_router.include_router(system.router)

api_router = api_v1_router
