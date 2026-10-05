"""
Agregador de rutas de API v1 y aliases raíz para compatibilidad hacia atrás.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.library import router as library_router
from app.api.v1.media import router as media_router
from app.api.v1.playback import router as playback_router
from app.api.v1.system import router as system_router

# Router agrupado bajo el prefijo canónico /api/v1
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(playback_router)
api_v1_router.include_router(library_router)
api_v1_router.include_router(media_router)
api_v1_router.include_router(system_router)

# Router legacy: expone endpoints de primer nivel y /api/weather/preview para compatibilidad con el frontend
legacy_router = APIRouter()
legacy_router.include_router(playback_router)
legacy_router.include_router(library_router)
legacy_router.include_router(media_router)
legacy_router.include_router(system_router, prefix="/api")
