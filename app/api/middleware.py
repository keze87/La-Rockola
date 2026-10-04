"""
Middleware para resolución de subrutas y proxys inversos (SubpathMiddleware).
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.dependencies import get_state


class SubpathMiddleware:
	"""
	Permite que La Rockola responda tanto en la raíz '/' como en un subpath configurable
	(por ejemplo '/rockola' cuando se accede via 'http://server.local/rockola').
	Soporta tanto peticiones HTTP como conexiones WebSocket.
	"""

	def __init__(self, app: ASGIApp) -> None:
		self.app = app

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		state = get_state()
		subpath = getattr(state, "subpath", "") if state else ""

		if subpath and scope.get("type") in ("http", "websocket"):
			path = scope.get("path", "")
			if path == subpath and scope.get("type") == "http":
				query_str = scope.get("query_string", b"").decode("latin1")
				location = f"{subpath}/" + (f"?{query_str}" if query_str else "")
				response_headers = [
					(b"location", location.encode("latin1")),
					(b"content-length", b"0"),
				]
				await send(
					{
						"type": "http.response.start",
						"status": 307,
						"headers": response_headers,
					}
				)
				await send(
					{
						"type": "http.response.body",
						"body": b"",
					}
				)
				return
			elif path.startswith(f"{subpath}/"):
				new_path = path[len(subpath) :] or "/"
				scope = dict(scope)
				scope["path"] = new_path
				current_root = scope.get("root_path", "")
				scope["root_path"] = f"{current_root}{subpath}"

		await self.app(scope, receive, send)
