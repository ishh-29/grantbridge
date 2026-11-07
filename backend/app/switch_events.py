"""Persistent Switch event consumer; subscribes without claiming rooms."""
import asyncio
import json
import logging
from uuid import uuid4
from urllib.parse import urlencode

import websockets
import httpx
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Application, WorkflowEvent, SwitchCursor
from app.settings import settings

log = logging.getLogger(__name__)


class SwitchConnection:
    def __init__(self):
        self.ready = asyncio.Event()
        self.room_lock = asyncio.Lock()
        self.connection_id = ""

    async def call(self, operation: str, arguments: dict, room_id: str | None = None):
        if not self.ready.is_set():
            try:
                await asyncio.wait_for(self.ready.wait(), timeout=15)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("Switch agent event connection is not ready") from exc
        headers = {"Authorization": f"Bearer {settings.switch_agent_api_key}"}
        if room_id:
            async with self.room_lock:
                await self._operation("connect_to_room", {"room_id": room_id}, headers)
                return await self._operation(operation, arguments, headers, self.connection_id)
        return await self._operation(operation, arguments, headers)

    async def _operation(self, operation: str, arguments: dict, headers: dict, connection_id: str | None = None):
        call_headers = dict(headers)
        if connection_id:
            call_headers["X-Switch-Connection-Id"] = connection_id
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.switch_base_url.rstrip('/')}/agents/{settings.switch_agent_id}/ops/{operation}",
                headers=call_headers,
                json=arguments,
            )
            return response.json().get("result")


switch_connection = SwitchConnection()


def switch_ws_url(base: str, query: dict[str, str]) -> str:
    scheme = "wss" if base.startswith("https://") else "ws"
    host = base.removeprefix("https://").removeprefix("http://").rstrip("/")
    return f"{scheme}://{host}/agents/{settings.switch_agent_id}/connection/ws?{urlencode(query)}"


def cursor_row(db):
    row = db.get(SwitchCursor, 1)
    if row is None:
        row = SwitchCursor(id=1, connection_id=str(uuid4()), cursor=0, generation="")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def persist_event(frame: dict) -> tuple[int, str, str] | None:
    data = frame.get("data") or {}
    if data.get("type") != "message":
        return None
    payload = data.get("payload") or {}
    room_id = data.get("room_id")
    event_id = str(frame.get("id") or data.get("sequence") or "")
    if not room_id or not event_id:
        return None
    body = payload.get("body")
    if not body:
        return None
    with SessionLocal() as db:
        app = db.scalar(select(Application).where(Application.switch_room_id == str(room_id)))
        if not app or db.scalar(select(WorkflowEvent).where(WorkflowEvent.switch_event_id == event_id)):
            return None
        actor = payload.get("sender_name") or "Switch participant"
        db.add(WorkflowEvent(application_id=app.id, actor=actor, event_type="switch_message",
            detail=str(body), source="switch", switch_event_id=event_id))
        db.commit()
        return app.id, str(actor), str(body)


async def run_switch_event_listener(stop: asyncio.Event) -> None:
    if not (settings.switch_base_url and settings.switch_agent_id and settings.switch_agent_api_key):
        return
    delay = 1
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                state = cursor_row(db)
                connection_id, cursor, generation = state.connection_id, state.cursor, state.generation
            switch_connection.connection_id = connection_id
            query = {"connection_id": connection_id, "scope": "all", "filter": "all",
                     "start_from": str(cursor) if cursor else "head", "client": "grantbridge-backend",
                     "client_version": "0.1.0"}
            if generation:
                query["expected_generation"] = generation
            headers = {"Authorization": f"Bearer {settings.switch_agent_api_key}"}
            async with websockets.connect(switch_ws_url(settings.switch_base_url, query),
                    additional_headers=headers, ping_interval=None, max_size=1_048_576) as ws:
                delay = 1
                async for raw in ws:
                    frame = json.loads(raw)
                    kind = frame.get("event")
                    data = frame.get("data") or {}
                    if kind == "connection_state":
                        with SessionLocal() as db:
                            state = cursor_row(db)
                            state.cursor = int(data.get("cursor") or 0)
                            state.generation = int(data.get("generation") or 0)
                            db.commit()
                        switch_connection.ready.set()
                    elif kind == "ping":
                        with SessionLocal() as db:
                            cursor = cursor_row(db).cursor
                        await ws.send(json.dumps({"type": "pong", "cursor": cursor}))
                    elif kind == "message":
                        routed = persist_event(frame)
                        with SessionLocal() as db:
                            state = cursor_row(db)
                            state.cursor = max(state.cursor, int(frame.get("id") or data.get("sequence") or 0))
                            db.commit()
                        if routed:
                            from app.workflow_router import route_agent_reply
                            asyncio.create_task(route_agent_reply(*routed))
                    elif kind == "gap":
                        with SessionLocal() as db:
                            state = cursor_row(db)
                            state.cursor = int(data.get("resumed_at") or state.cursor)
                            db.commit()
                        log.warning("Switch event gap; durable room history must be reconciled for missed events")
                    elif kind in {"refused", "evicted"}:
                        log.warning("Switch event stream closed: %s", data)
                        break
        except asyncio.CancelledError:
            switch_connection.ready.clear()
            raise
        except Exception:
            switch_connection.ready.clear()
            log.exception("Switch event stream disconnected")
        finally:
            switch_connection.ready.clear()
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except asyncio.TimeoutError:
            delay = min(delay * 2, 30)
