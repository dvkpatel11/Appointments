"""Tests for the in-process pub/sub EventBus.

These run without the database, so they're fast and self-contained. The goal
is to bootstrap the test suite — subsequent tests can add DB fixtures, but
this file is intentionally hermetic.
"""
from __future__ import annotations

import threading
import time

from src.infrastructure.event_bus import (
    EVT_ALERT,
    EVT_LOG_LINE,
    Event,
    EventBus,
)


def test_publish_then_consume():
    bus = EventBus()
    sid = bus.subscribe()
    try:
        bus.publish(Event(type=EVT_ALERT, data={"msg": "hi"}))
        evt = bus.get(sid, timeout=0.5)
        assert evt is not None
        assert evt.type == EVT_ALERT
        assert evt.data == {"msg": "hi"}
    finally:
        bus.unsubscribe(sid)


def test_subscribe_isolates_subscribers():
    bus = EventBus()
    a = bus.subscribe()
    b = bus.subscribe()
    try:
        bus.publish(Event(type=EVT_LOG_LINE, data={"client_id": "x"}))
        ea = bus.get(a, timeout=0.2)
        eb = bus.get(b, timeout=0.2)
        assert ea is not None
        assert eb is not None
        # Each subscriber has its own queue; draining one doesn't affect the other.
        assert ea.type == eb.type == EVT_LOG_LINE
        assert ea.data == eb.data == {"client_id": "x"}
        # After draining subscriber A, B's event is still there.
        bus.drain(a)
        assert bus.get(a, timeout=0.1) is None
        assert bus.get(b, timeout=0.1) is None  # already drained above by .get()
        # And unsubscribing A doesn't affect B.
        bus.unsubscribe(a)
        # B should still be subscribed.
        assert bus.is_subscribed(b)
    finally:
        bus.unsubscribe(b)


def test_get_times_out_when_empty():
    bus = EventBus()
    sid = bus.subscribe()
    try:
        t0 = time.time()
        evt = bus.get(sid, timeout=0.1)
        elapsed = time.time() - t0
        assert evt is None
        assert 0.05 <= elapsed < 0.5
    finally:
        bus.unsubscribe(sid)


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    sid = bus.subscribe()
    bus.unsubscribe(sid)
    bus.publish(Event(type=EVT_ALERT, data={}))
    assert bus.get(sid, timeout=0.1) is None


def test_publish_does_not_block_when_subscriber_queue_full():
    bus = EventBus()
    sid = bus.subscribe()
    try:
        # 1024 is the default qmax; publish > qmax events and assert publish returns.
        for i in range(2000):
            bus.publish(Event(type=EVT_ALERT, data={"i": i}))
        # No assertion on delivery — the contract is "non-blocking"; some
        # events will be dropped and that's expected.
    finally:
        bus.unsubscribe(sid)


def test_drain_returns_all_buffered():
    bus = EventBus()
    sid = bus.subscribe()
    try:
        for i in range(5):
            bus.publish(Event(type=EVT_ALERT, data={"i": i}))
        drained = bus.drain(sid)
        assert len(drained) == 5
        assert [e.data["i"] for e in drained] == [0, 1, 2, 3, 4]
    finally:
        bus.unsubscribe(sid)


def test_publish_simple_helper():
    bus = EventBus()
    sid = bus.subscribe()
    try:
        bus.publish_simple(EVT_LOG_LINE, client_id="abc", line="hello")
        evt = bus.get(sid, timeout=0.2)
        assert evt is not None
        assert evt.type == EVT_LOG_LINE
        assert evt.data == {"client_id": "abc", "line": "hello"}
    finally:
        bus.unsubscribe(sid)


def test_thread_safety_under_concurrent_publishers():
    bus = EventBus()
    sid = bus.subscribe()
    n_publishers = 4
    n_per_publisher = 100

    def worker(idx: int) -> None:
        for i in range(n_per_publisher):
            bus.publish(Event(type=EVT_ALERT, data={"p": idx, "i": i}))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_publishers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Drain whatever arrived; just assert no deadlock / crash.
    drained = bus.drain(sid, max_items=10_000)
    # We expect 0–1024 events to have made it (queue is bounded).
    assert len(drained) <= 1024
    bus.unsubscribe(sid)


def test_stats_reports_subscribers():
    bus = EventBus()
    assert bus.subscriber_count() == 0
    a = bus.subscribe()
    b = bus.subscribe()
    assert bus.subscriber_count() == 2
    bus.unsubscribe(a)
    assert bus.subscriber_count() == 1
    bus.unsubscribe(b)
    assert bus.subscriber_count() == 0


def test_event_serialization():
    e = Event(type=EVT_ALERT, data={"k": "v"}, ts=1.0, id=42)
    d = e.to_dict()
    assert d["type"] == EVT_ALERT
    assert d["data"] == {"k": "v"}
    assert d["ts"] == 1.0
    assert d["id"] == 42
