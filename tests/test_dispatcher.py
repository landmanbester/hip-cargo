"""Tests for the centralised event dispatcher."""

import asyncio
import concurrent.futures

import pytest

from hip_cargo.monitoring.dispatcher import EventDispatcher

# --- Fake aggregator for dispatcher tests ---


class _FakeRef:
    def __init__(self, value):
        self._value = value

    def future(self):
        f = concurrent.futures.Future()
        f.set_result(self._value)
        return f


class _RemoteMethod:
    def __init__(self, fn):
        self._fn = fn

    def remote(self, *args, **kwargs):
        return _FakeRef(self._fn(*args, **kwargs))


class FakeAggregator:
    """Minimal fake aggregator for dispatcher tests — only needs get_events."""

    def __init__(self):
        self._events: dict[str, list[dict]] = {}
        self.get_events = _RemoteMethod(self._get_events)

    def push(self, job_id: str, event: dict):
        """Test helper: add an event."""
        if job_id not in self._events:
            self._events[job_id] = []
        self._events[job_id].append(event)

    def _get_events(self, job_id, since_index=0):
        return self._events.get(job_id, [])[since_index:]


# --- Tests ---


def test_subscribe_unsubscribe():
    """Subscribe increases count, unsubscribe decreases it."""
    agg = FakeAggregator()
    dispatcher = EventDispatcher(agg, poll_interval=0.1)

    queue, sub_id = dispatcher.subscribe("job1")
    assert dispatcher.active_subscriptions == 1
    assert dispatcher.active_jobs == 1

    dispatcher.unsubscribe("job1", sub_id)
    assert dispatcher.active_subscriptions == 0
    assert dispatcher.active_jobs == 0


def test_multiple_subscribers_same_job():
    """Multiple subscribers to the same job are tracked correctly."""
    agg = FakeAggregator()
    dispatcher = EventDispatcher(agg, poll_interval=0.1)

    _, sub1 = dispatcher.subscribe("job1")
    _, sub2 = dispatcher.subscribe("job1")
    _, sub3 = dispatcher.subscribe("job1")
    assert dispatcher.active_subscriptions == 3
    assert dispatcher.active_jobs == 1

    dispatcher.unsubscribe("job1", sub2)
    assert dispatcher.active_subscriptions == 2


def test_multiple_jobs():
    """Subscribers to different jobs are tracked independently."""
    agg = FakeAggregator()
    dispatcher = EventDispatcher(agg, poll_interval=0.1)

    dispatcher.subscribe("job1")
    dispatcher.subscribe("job2")
    assert dispatcher.active_subscriptions == 2
    assert dispatcher.active_jobs == 2


def test_unsubscribe_cleans_up_cursors():
    """When all subscribers for a job are gone, cursors are cleaned up."""
    agg = FakeAggregator()
    dispatcher = EventDispatcher(agg, poll_interval=0.1)

    _, sub_id = dispatcher.subscribe("job1")
    assert "job1" in dispatcher._cursors

    dispatcher.unsubscribe("job1", sub_id)
    assert "job1" not in dispatcher._subscriptions
    assert "job1" not in dispatcher._cursors


@pytest.mark.asyncio
async def test_start_stop():
    """Start sets _running and creates a task, stop cancels it."""
    agg = FakeAggregator()
    dispatcher = EventDispatcher(agg, poll_interval=0.1)

    dispatcher.start()
    assert dispatcher._running is True
    assert dispatcher._task is not None

    await dispatcher.stop()
    assert dispatcher._running is False
    assert dispatcher._task is None


@pytest.mark.asyncio
async def test_events_dispatched_to_queue():
    """Events from the aggregator are dispatched to subscriber queues."""
    agg = FakeAggregator()
    agg.push("job1", {"event_type": "started", "step": 0})
    agg.push("job1", {"event_type": "progress", "step": 1})

    dispatcher = EventDispatcher(agg, poll_interval=0.05)
    queue, sub_id = dispatcher.subscribe("job1")

    dispatcher.start()
    try:
        # Wait for events to appear
        event1 = await asyncio.wait_for(queue.get(), timeout=2.0)
        event2 = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert event1["event_type"] == "started"
        assert event2["event_type"] == "progress"
    finally:
        dispatcher.unsubscribe("job1", sub_id)
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_events_fan_out_to_multiple_subscribers():
    """All subscribers for the same job receive the same events."""
    agg = FakeAggregator()
    agg.push("job1", {"event_type": "started"})

    dispatcher = EventDispatcher(agg, poll_interval=0.05)
    q1, sub1 = dispatcher.subscribe("job1")
    q2, sub2 = dispatcher.subscribe("job1")
    q3, sub3 = dispatcher.subscribe("job1")

    dispatcher.start()
    try:
        for q in (q1, q2, q3):
            event = await asyncio.wait_for(q.get(), timeout=2.0)
            assert event["event_type"] == "started"
    finally:
        dispatcher.unsubscribe("job1", sub1)
        dispatcher.unsubscribe("job1", sub2)
        dispatcher.unsubscribe("job1", sub3)
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_jobs_isolated():
    """Subscribers only receive events for their subscribed job."""
    agg = FakeAggregator()
    agg.push("job1", {"event_type": "started", "job": "job1"})
    agg.push("job2", {"event_type": "started", "job": "job2"})

    dispatcher = EventDispatcher(agg, poll_interval=0.05)
    q1, sub1 = dispatcher.subscribe("job1")
    q2, sub2 = dispatcher.subscribe("job2")

    dispatcher.start()
    try:
        e1 = await asyncio.wait_for(q1.get(), timeout=2.0)
        e2 = await asyncio.wait_for(q2.get(), timeout=2.0)
        assert e1["job"] == "job1"
        assert e2["job"] == "job2"
        # Queues should be empty — no cross-contamination
        assert q1.empty()
        assert q2.empty()
    finally:
        dispatcher.unsubscribe("job1", sub1)
        dispatcher.unsubscribe("job2", sub2)
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_dead_subscriber_cleanup():
    """Full queue causes subscriber to be removed."""
    agg = FakeAggregator()
    dispatcher = EventDispatcher(agg, poll_interval=0.05)

    # Create a queue with maxsize=1 so it overflows easily
    queue = asyncio.Queue(maxsize=1)
    sub_id = "job1_dead"
    dispatcher._subscriptions["job1"] = {(queue, sub_id)}
    dispatcher._cursors["job1"] = 0

    # Push multiple events to overflow the queue
    for i in range(5):
        agg.push("job1", {"event_type": "progress", "step": i})

    dispatcher.start()
    try:
        # Wait for a poll cycle to detect the dead subscriber
        await asyncio.sleep(0.2)
        # The dead subscriber should have been cleaned up
        assert dispatcher.active_subscriptions == 0
    finally:
        await dispatcher.stop()
