"""In-process pub/sub for SSE subscribers.

The orchestrator runs scrapers in separate ``multiprocessing.Process`` workers,
so cross-process delivery is impossible with an in-memory bus. Within the web
process, this bus is enough for events triggered by web actions (admin
approves, settings change, etc.) and for the SSE poller thread that detects
scraper-side changes by reading SQLite + log file mtimes.

Design:
- Publishers are non-blocking: ``publish`` drops events to a slow subscriber
  rather than wait.
- Each subscriber gets a bounded ``queue.Queue``; the SSE handler drains it.
- Subscribers can unsubscribe safely from inside their own callbacks.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("usvisa")

SubscriberId = str

# Event types. Keep the public surface small; the SSE handler maps these to
# the wire names documented in docs/ui-design.md §6.
EVT_STATE_CHANGED = "state.changed"
EVT_LOG_LINE = "log.line"
EVT_SCREENSHOT_READY = "screenshot.ready"
EVT_METRIC_TICK = "metric.tick"
EVT_REQUEST_NEW = "request.new"
EVT_ALERT = "alert"
EVT_HEALTH = "health"


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data, "ts": self.ts, "id": self.id}


class _Subscription:
    __slots__ = ("id", "queue", "created_at")

    def __init__(self, sub_id: SubscriberId, qmax: int = 1024) -> None:
        self.id = sub_id
        self.queue: queue.Queue[Event] = queue.Queue(maxsize=qmax)
        self.created_at = time.time()


class EventBus:
    """Thread-safe pub/sub.

    Usage:
        bus = EventBus()
        sub_id = bus.subscribe()
        try:
            bus.publish(Event(type=EVT_ALERT, data={"msg": "hi"}))
            while True:
                evt = bus.get(sub_id, timeout=1.0)
                ...
        finally:
            bus.unsubscribe(sub_id)
    """

    def __init__(self) -> None:
        self._subs: dict[SubscriberId, _Subscription] = {}
        self._lock = threading.Lock()
        self._next_id = 0
        self._dropped: dict[SubscriberId, int] = {}

    # ── subscription lifecycle ────────────────────────────────────────
    def subscribe(self, sub_id: SubscriberId | None = None) -> SubscriberId:
        with self._lock:
            if sub_id is None:
                sub_id = f"sub-{self._next_id}-{int(time.time() * 1000)}"
                self._next_id += 1
            if sub_id in self._subs:
                # Replace queue but keep id; SSE reconnects with new id each
                # time so this is rare.
                self._subs[sub_id].queue = queue.Queue(maxsize=1024)
            else:
                self._subs[sub_id] = _Subscription(sub_id)
                self._dropped[sub_id] = 0
            return sub_id

    def unsubscribe(self, sub_id: SubscriberId) -> None:
        with self._lock:
            self._subs.pop(sub_id, None)
            self._dropped.pop(sub_id, None)

    def is_subscribed(self, sub_id: SubscriberId) -> bool:
        with self._lock:
            return sub_id in self._subs

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    # ── publish / consume ─────────────────────────────────────────────
    def publish(self, event: Event) -> None:
        with self._lock:
            subs = list(self._subs.values())
        for sub in subs:
            try:
                sub.queue.put_nowait(event)
            except queue.Full:
                self._dropped[sub.id] = self._dropped.get(sub.id, 0) + 1

    def publish_simple(self, type_: str, **data: Any) -> None:
        self.publish(Event(type=type_, data=data))

    def get(self, sub_id: SubscriberId, timeout: float) -> Event | None:
        sub = self._subs.get(sub_id)
        if sub is None:
            return None
        try:
            return sub.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self, sub_id: SubscriberId, max_items: int = 256) -> list[Event]:
        """Return all events currently buffered (non-blocking)."""
        sub = self._subs.get(sub_id)
        if sub is None:
            return []
        events: list[Event] = []
        for _ in range(max_items):
            try:
                events.append(sub.queue.get_nowait())
            except queue.Empty:
                break
        return events

    def dropped_count(self, sub_id: SubscriberId) -> int:
        with self._lock:
            return self._dropped.get(sub_id, 0)

    # ── diagnostics ───────────────────────────────────────────────────
    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "subscribers": len(self._subs),
                "queue_sizes": {sid: s.queue.qsize() for sid, s in self._subs.items()},
                "dropped_total": sum(self._dropped.values()),
            }


# ── Module-level singleton ──────────────────────────────────────────
_bus: EventBus | None = None
_bus_lock = threading.Lock()


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus


def reset_bus() -> None:
    """Test helper — drops the singleton."""
    global _bus
    with _bus_lock:
        _bus = None


# ── Background poller ────────────────────────────────────────────────
# The scraper processes can't talk to us, so we poll the shared SQLite
# database for changes. The poller reads ``updated_at`` columns and emits
# diff events. The poller runs as a daemon thread inside the web process.


class ChangePoller:
    """Poll SQLite + log files; emit events when something changes.

    Cheap to run: each tick issues 2-3 SELECTs. Tick interval defaults to 1.5s
    which is below human perception for status displays.
    """

    def __init__(self, bus: EventBus, interval: float = 1.5) -> None:
        self.bus = bus
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_clients_updated: str | None = None
        self._last_state_updated: str | None = None
        self._log_positions: dict[str, int] = {}
        self._screenshot_seen: set[str] = set()
        self._request_count: int = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ChangePoller", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        from pathlib import Path

        from src.config import settings
        from src.infrastructure.database import cursor

        while not self._stop.is_set():
            try:
                # 1. Clients table — max(updated_at) tells us if anything changed.
                with cursor() as cur:
                    cur.execute("SELECT MAX(updated_at) FROM clients")
                    row = cur.fetchone()
                    cur.execute("SELECT COUNT(*) FROM clients WHERE state = 'pending'")
                    pending = cur.fetchone()[0]
                last = row[0] if row else None
                if last and last != self._last_clients_updated:
                    if self._last_clients_updated is not None:
                        self.bus.publish_simple(EVT_STATE_CHANGED, table="clients")
                    self._last_clients_updated = last

                # 2. Automation state — any change → publish.
                with cursor() as cur:
                    cur.execute("SELECT MAX(updated_at) FROM automation_state")
                    row = cur.fetchone()
                last = row[0] if row else None
                if last and last != self._last_state_updated:
                    if self._last_state_updated is not None:
                        self.bus.publish_simple(EVT_STATE_CHANGED, table="automation_state")
                    self._last_state_updated = last

                # 3. New requests — poll count.
                with cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM clients WHERE state = 'pending'")
                    n = cur.fetchone()[0]
                if n > self._request_count:
                    self.bus.publish_simple(EVT_REQUEST_NEW, count=n - self._request_count)
                self._request_count = n

                # 4. Log file tails — for each client, read new lines since last poll.
                log_dir = Path(settings.log_dir)
                if log_dir.is_dir():
                    for log_file in log_dir.glob("*.log"):
                        client_id = log_file.stem
                        if client_id == "server":
                            continue
                        try:
                            size = log_file.stat().st_size
                            last = self._log_positions.get(client_id, 0)
                            if size > last:
                                with log_file.open("r", errors="replace") as f:
                                    f.seek(last)
                                    new = f.read()
                                self._log_positions[client_id] = size
                                # Split into lines; emit last one only to keep noise down.
                                lines = [ln for ln in new.splitlines() if ln.strip()]
                                if lines:
                                    last_line = lines[-1]
                                    self.bus.publish_simple(
                                        EVT_LOG_LINE,
                                        client_id=client_id,
                                        line=last_line,
                                        ts=time.time(),
                                    )
                        except OSError:
                            pass

                # 5. Screenshots — for each client dir, emit if newer than last seen.
                shot_root = Path(settings.screenshot_base)
                if shot_root.is_dir():
                    for client_dir in shot_root.iterdir():
                        if not client_dir.is_dir():
                            continue
                        try:
                            files = sorted(client_dir.glob("*.png"))
                        except OSError:
                            continue
                        for f in files:
                            key = f"{client_dir.name}/{f.name}"
                            if key in self._screenshot_seen:
                                continue
                            self._screenshot_seen.add(key)
                            if len(self._screenshot_seen) > 5000:
                                # Bound memory; only relevant during a long session.
                                self._screenshot_seen = set(list(self._screenshot_seen)[-2000:])
                            self.bus.publish_simple(
                                EVT_SCREENSHOT_READY,
                                client_id=client_dir.name,
                                path=str(f),
                                ts=f.stat().st_mtime,
                            )

                # 6. Metric tick — every poll is fine; SSE handler rate-limits.
                self.bus.publish_simple(
                    EVT_METRIC_TICK,
                    pending=pending,
                    ts=time.time(),
                )

            except Exception as e:
                # Never let the poller die.
                logger.warning("Change poller tick failed: %s", e)

            self._stop.wait(self.interval)


_poller: ChangePoller | None = None
_poller_lock = threading.Lock()


def get_poller() -> ChangePoller:
    global _poller
    if _poller is None:
        with _poller_lock:
            if _poller is None:
                _poller = ChangePoller(get_bus())
    return _poller
