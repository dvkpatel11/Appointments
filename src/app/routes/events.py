"""Server-Sent Events endpoint.

The browser opens one ``EventSource`` to ``/events/stream`` and receives
streamed JSON events. The Flask generator yields ``data: <json>\\n\\n``
lines with an ``event:`` field for typed handlers on the client.

Authentication: reuses the existing Flask session cookie. ``before_request``
hooks aren't relevant here — the route itself checks ``session.get("authenticated")``.
Unauthenticated clients get a 401 immediately.

Lifecycle: each connection registers a subscription on the in-process bus,
then the generator yields events as they arrive. Cancellation (``generator
close``) unsubscribes cleanly.
"""

from __future__ import annotations

import json
import time
from typing import Any

from flask import Blueprint, Response, session, stream_with_context

from src.infrastructure.event_bus import (
    EVT_HEALTH,
    EventBus,
    get_bus,
    get_poller,
)

bp = Blueprint("events", __name__, url_prefix="/events")

# Emit at most one health ping per this interval even if no events arrive,
# so the browser's EventSource knows the connection is alive.
HEARTBEAT_INTERVAL = 15.0

# Coalesce noisy events — at most one of these per window per type.
COALESCE_WINDOW = 0.5


def _is_authed() -> bool:
    return bool(session.get("authenticated"))


def _format_sse(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    """Serialize one SSE frame."""
    payload = json.dumps(data, default=str, separators=(",", ":"))
    frame = f"event: {event}\n"
    if event_id is not None:
        frame += f"id: {event_id}\n"
    # Split on newlines so multi-line data doesn't break SSE framing.
    for line in payload.splitlines() or [""]:
        frame += f"data: {line}\n"
    return frame + "\n"


@bp.route("/stream")
def stream():
    if not _is_authed():
        return Response("unauthorized", status=401)

    bus: EventBus = get_bus()
    sub_id = bus.subscribe()

    @stream_with_context
    def gen():
        last_emit: dict[str, float] = {}
        last_heartbeat = time.time()
        # Monotonic counter per connection for Last-Event-ID.
        next_id = 0
        try:
            # Initial comment so the browser knows the stream is open.
            yield ": connected\n\n"
            while True:
                evt = bus.get(sub_id, timeout=1.0)
                if evt is not None:
                    now = time.time()
                    last = last_emit.get(evt.type, 0.0)
                    if now - last < COALESCE_WINDOW and evt.type not in (EVT_HEALTH,):
                        # Skip — the next emit will carry the freshest state
                        # because poller re-publishes on the next tick.
                        continue
                    last_emit[evt.type] = now
                    next_id += 1
                    yield _format_sse(evt.type, evt.to_dict(), event_id=next_id)
                else:
                    if time.time() - last_heartbeat >= HEARTBEAT_INTERVAL:
                        last_heartbeat = time.time()
                        next_id += 1
                        yield _format_sse(
                            EVT_HEALTH,
                            {"ts": last_heartbeat},
                            event_id=next_id,
                        )
        except GeneratorExit:
            pass
        finally:
            bus.unsubscribe(sub_id)

    resp = Response(gen(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"  # Nginx: don't buffer
    resp.headers["Connection"] = "keep-alive"
    return resp


def start_poller_once() -> None:
    """Idempotent — call from create_app()."""
    get_poller().start()
