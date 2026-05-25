"""Socket.IO real-time events for live calls dashboard."""

import socketio

from app.core.config import settings

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=settings.cors_origins_list)
sio_app = socketio.ASGIApp(sio, socketio_path="/socket.io")


class SocketManager:
    async def emit_call_update(self, client_id: int, data: dict) -> None:
        await sio.emit("call_update", data, room=f"client_{client_id}")

    async def emit_transcript(self, client_id: int, call_id: int, entry: dict) -> None:
        await sio.emit(
            "transcript",
            {"call_id": call_id, **entry},
            room=f"client_{client_id}",
        )

    async def emit_sentiment(self, client_id: int, call_id: int, score: float) -> None:
        await sio.emit(
            "sentiment",
            {"call_id": call_id, "score": score},
            room=f"client_{client_id}",
        )


socket_manager = SocketManager()


@sio.event
async def connect(sid, environ, auth=None):
    client_id = (auth or {}).get("client_id")
    if client_id:
        await sio.enter_room(sid, f"client_{client_id}")


@sio.event
async def disconnect(sid):
    pass


@sio.event
async def join_call(sid, data):
    call_id = data.get("call_id")
    if call_id:
        await sio.enter_room(sid, f"call_{call_id}")
