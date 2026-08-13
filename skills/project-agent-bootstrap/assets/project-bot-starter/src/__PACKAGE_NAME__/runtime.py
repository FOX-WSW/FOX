"""Small orchestration boundary for concrete Feishu and Agent adapters."""

from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

from .policy import require_allowed_chat
from .state import StateStore


@dataclass(frozen=True)
class IncomingEvent:
    event_id: str
    message_id: str
    chat_id: str
    topic_id: str
    requester_id: str
    text: str


class AgentRuntime(Protocol):
    def resolve_thread(self, topic_id: str) -> str: ...

    def run_turn(self, thread_id: str, event: IncomingEvent) -> str: ...


class DeliveryAdapter(Protocol):
    def persist_answer(self, event: IncomingEvent, answer: str) -> Path: ...

    def deliver_answer(self, event: IncomingEvent, answer_path: Path) -> str:
        """Deliver idempotently using event.message_id and return the Feishu message ID."""

        ...


class TopicProcessor:
    """Process one already-serialized topic event with durable checkpoints."""

    def __init__(
        self,
        *,
        state: StateStore,
        runtime: AgentRuntime,
        delivery: DeliveryAdapter,
        allowed_chat_ids: frozenset[str],
        worker_id: str | None = None,
        lease_seconds: int = 300,
    ):
        self.state = state
        self.runtime = runtime
        self.delivery = delivery
        self.allowed_chat_ids = allowed_chat_ids
        self.worker_id = worker_id or uuid.uuid4().hex
        if lease_seconds < 3:
            raise ValueError("lease_seconds must be at least 3")
        self.lease_seconds = lease_seconds

    @contextmanager
    def _lease_heartbeat(self, event_id: str, lease_token: int) -> Iterator[None]:
        stop = threading.Event()
        interval = max(1.0, min(60.0, self.lease_seconds / 3))

        def renew() -> None:
            while not stop.wait(interval):
                try:
                    self.state.renew_lease(
                        event_id,
                        worker_id=self.worker_id,
                        lease_token=lease_token,
                        lease_seconds=self.lease_seconds,
                    )
                except Exception:
                    return

        heartbeat = threading.Thread(
            target=renew,
            name=f"lease-heartbeat-{event_id[:12]}",
            daemon=True,
        )
        heartbeat.start()
        try:
            yield
        finally:
            stop.set()
            heartbeat.join(timeout=1)

    def process(self, event: IncomingEvent) -> str:
        require_allowed_chat(event.chat_id, self.allowed_chat_ids)
        claimed = self.state.claim_event(event.event_id, event.message_id, event.topic_id)
        if not claimed:
            existing = self.state.get_turn(event.event_id) or self.state.get_turn_by_message(
                event.message_id
            )
            if existing is None or existing.status not in {"received", "retry_pending"}:
                return "duplicate"
        else:
            existing = self.state.get_turn(event.event_id)
        canonical_event_id = existing.event_id
        lease_token = self.state.claim_for_run(
            canonical_event_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if lease_token is None:
            return "queued"
        try:
            with self._lease_heartbeat(canonical_event_id, lease_token):
                current = self.state.get_turn(canonical_event_id)
                if current.answer_path:
                    answer_path = Path(current.answer_path)
                    self.state.transition(
                        canonical_event_id,
                        "delivery_pending",
                        worker_id=self.worker_id,
                        lease_token=lease_token,
                    )
                else:
                    thread_id = self.state.thread_for_topic(event.topic_id)
                    if thread_id is None:
                        thread_id = self.runtime.resolve_thread(event.topic_id)
                        self.state.bind_topic(event.topic_id, thread_id)
                    answer = self.runtime.run_turn(thread_id, event)
                    answer_path = self.delivery.persist_answer(event, answer)
                    self.state.transition(
                        canonical_event_id,
                        "answer_persisted",
                        answer_path=str(answer_path),
                        worker_id=self.worker_id,
                        lease_token=lease_token,
                    )
                    self.state.transition(
                        canonical_event_id,
                        "delivery_pending",
                        worker_id=self.worker_id,
                        lease_token=lease_token,
                    )
                external_message_id = self.delivery.deliver_answer(event, answer_path)
                self.state.transition(
                    canonical_event_id,
                    "delivered",
                    external_message_id=external_message_id,
                    worker_id=self.worker_id,
                    lease_token=lease_token,
                )
                self.state.transition(
                    canonical_event_id,
                    "completed",
                    worker_id=self.worker_id,
                    lease_token=lease_token,
                )
            return "completed"
        except Exception:
            turn = self.state.get_turn(canonical_event_id)
            if turn and turn.status in {"running", "answer_persisted", "delivery_pending"}:
                try:
                    self.state.schedule_retry(
                        canonical_event_id,
                        error_code="turn_or_delivery_error",
                        delay_seconds=30,
                        worker_id=self.worker_id,
                        lease_token=lease_token,
                    )
                except ValueError:
                    pass
            raise
