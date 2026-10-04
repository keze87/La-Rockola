"""
Esquemas Pydantic V2 para validación exhaustiva de payloads HTTP y eventos WebSocket.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse[T](BaseModel):
	"""Respuesta estándar de la API REST."""

	model_config = ConfigDict(extra="allow")

	status: str = Field(default="ok", description="Estado de la operación ('ok' o 'error')")
	data: T | None = Field(default=None, description="Datos devueltos por la operación")


class CommandRequest(BaseModel):
	"""Payload para comandos de control de reproducción y gestión de cola/historial."""

	model_config = ConfigDict(extra="allow")

	cmd: str = Field(..., description="Nombre del comando a ejecutar")
	path: str | None = Field(default=None, description="Ruta de archivo o URL")
	amount: float | None = Field(default=None, description="Cantidad de segundos para salto de tiempo")
	vollevel: float | None = Field(default=None, description="Nivel de volumen (0 a 100)")
	state: bool | None = Field(default=None, description="Estado booleano para toggles (mute, dj, etc.)")
	index: int | None = Field(default=None, description="Índice en la cola o historial")
	new_index: int | None = Field(default=None, description="Nuevo índice para reordenamiento")
	history_index: int | None = Field(default=None, description="Índice de destino en historial")
	location: str | None = Field(default=None, description="Ubicación meteorológica")
	type: str | None = Field(default=None, description="Tipo de salto o entidad")


class TrackSchema(BaseModel):
	"""Esquema de una pista musical para respuestas de la API."""

	model_config = ConfigDict(extra="allow")

	path: str
	display_title: str
	display_artist: str
	album: str = "Desconocido"
	duration_str: str = "0:00"
	duration: float | None = None
	mood_score: float | None = None
	artist: str | None = None
	title: str | None = None
	track_hash: str | None = None
	count: int | None = None


class ScanStatusSchema(BaseModel):
	"""Estado del proceso de escaneo de la biblioteca musical."""

	is_scanning: bool = False
	is_analyzing_mood: bool = False
	phase: str = "idle"
	current: int = 0
	total: int = 0
	message: str = ""


# --- Esquemas para el protocolo WebSocket ---


class WebSocketMessage(BaseModel):
	"""Mensaje base para comunicación por WebSocket."""

	model_config = ConfigDict(extra="allow")

	type: str = Field(..., description="Tipo de evento")


class LocalPlayerClaim(WebSocketMessage):
	"""Solicitud del cliente web para convertirse en el reproductor de audio local."""

	type: str = "local_player_claim"


class LocalPlayerClaimResult(WebSocketMessage):
	"""Respuesta del servidor a la solicitud de reproductor local."""

	type: str = "local_player_claim_result"
	ok: bool = True


class LocalPlayerRelease(WebSocketMessage):
	"""Notificación del cliente liberando el rol de reproductor local."""

	type: str = "local_player_release"


class LocalPlayerUpdate(WebSocketMessage):
	"""Reporte periódico de posición y estado emitido por el reproductor local."""

	type: str = "local_player_update"
	time_pos: float | None = None
	duration: float | None = None
	paused: bool | None = None


class LocalPlayerSeek(WebSocketMessage):
	"""Notificación enviada por el servidor al reproductor local para ejecutar un seek remoto."""

	type: str = "local_player_seek"
	time_pos: float
	relative: bool = False
