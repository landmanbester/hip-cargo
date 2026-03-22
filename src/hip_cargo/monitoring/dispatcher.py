"""Centralised event dispatcher for WebSocket fan-out.

Polls the ProgressAggregator once per interval for all subscribed jobs
and pushes events to per-connection asyncio.Queue instances. This avoids
N separate aggregator calls for N connected WebSocket clients.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def _get_from_actor(ref):
    """Await a Ray object ref in an async context."""
    return await asyncio.wrap_future(ref.future())


class EventDispatcher:
    """Centralised event dispatcher that polls the aggregator and fans out
    to connected WebSocket clients via asyncio.Queue instances.

    One instance per FastAPI application, created in the lifespan.
    Runs a background asyncio.Task that polls at a fixed interval.
    """

    def __init__(self, aggregator, poll_interval: float = 0.5) -> None:
        self._aggregator = aggregator
        self._poll_interval = poll_interval
        # job_id -> set of (queue, subscription_id) tuples
        self._subscriptions: dict[str, set[tuple[asyncio.Queue, str]]] = {}
        # job_id -> last event index we've fetched
        self._cursors: dict[str, int] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """Start the background poll loop."""
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the background poll loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def subscribe(self, job_id: str) -> tuple[asyncio.Queue, str]:
        """Register a new subscriber for a job's events.

        Args:
            job_id: The job to subscribe to.

        Returns:
            A (queue, subscription_id) tuple. The caller should await
            queue.get() to receive events. Call unsubscribe() with the
            subscription_id when done.
        """
        queue: asyncio.Queue = asyncio.Queue()
        sub_id = f"{job_id}_{id(queue)}"
        if job_id not in self._subscriptions:
            self._subscriptions[job_id] = set()
            self._cursors[job_id] = 0
        self._subscriptions[job_id].add((queue, sub_id))
        return queue, sub_id

    def unsubscribe(self, job_id: str, sub_id: str) -> None:
        """Remove a subscriber.

        Args:
            job_id: The job the subscription was for.
            sub_id: The subscription ID returned by subscribe().
        """
        if job_id in self._subscriptions:
            self._subscriptions[job_id] = {(q, sid) for q, sid in self._subscriptions[job_id] if sid != sub_id}
            if not self._subscriptions[job_id]:
                del self._subscriptions[job_id]
                self._cursors.pop(job_id, None)

    async def _poll_loop(self) -> None:
        """Background loop that polls the aggregator and dispatches events."""
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in event dispatcher poll loop")
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        """Poll the aggregator for all subscribed jobs and dispatch events."""
        job_ids = list(self._subscriptions.keys())
        if not job_ids:
            return

        for job_id in job_ids:
            subs = self._subscriptions.get(job_id)
            if not subs:
                continue

            cursor = self._cursors.get(job_id, 0)
            try:
                events = await _get_from_actor(self._aggregator.get_events.remote(job_id, cursor))
            except Exception:
                continue  # aggregator unreachable, skip this cycle

            if not events:
                continue

            self._cursors[job_id] = cursor + len(events)

            # Fan out to all subscribers for this job
            dead_subs = set()
            for queue, sub_id in subs:
                try:
                    for event in events:
                        queue.put_nowait(event)
                except Exception:
                    dead_subs.add(sub_id)

            for sub_id in dead_subs:
                self.unsubscribe(job_id, sub_id)

    @property
    def active_subscriptions(self) -> int:
        """Total number of active subscriptions across all jobs."""
        return sum(len(subs) for subs in self._subscriptions.values())

    @property
    def active_jobs(self) -> int:
        """Number of jobs with at least one subscriber."""
        return len(self._subscriptions)
