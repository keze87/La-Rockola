"""
Capa de API de La Rockola del Carpincho.
Esquemas Pydantic V2, enrutadores HTTP y protocolo WebSocket.
"""

from app.api.schemas import ApiResponse, CommandRequest
from app.api.websocket import ConnectionManager

__all__ = ["ApiResponse", "CommandRequest", "ConnectionManager"]
