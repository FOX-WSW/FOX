from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from __PACKAGE_NAME__.runtime import IncomingEvent, TopicProcessor
from __PACKAGE_NAME__.state import StateStore


class FakeRuntime:
    def resolve_thread(self, topic_id: str) -> str:
        return f"thread-for-{topic_id}"

    def run_turn(self, thread_id: str, event: IncomingEvent) -> str:
        return f"{thread_id}: {event.text}"


class FakeDelivery:
    def __init__(self, root: Path):
        self.root = root
        self.delivered: list[str] = []

    def persist_answer(self, event: IncomingEvent, answer: str) -> Path:
        path = self.root / f"{event.event_id}.txt"
        path.write_text(answer, encoding="utf-8")
        return path

    def deliver_answer(self, event: IncomingEvent, answer_path: Path) -> str:
        self.delivered.append(answer_path.read_text(encoding="utf-8"))
        return f"reply-for-{event.message_id}"


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.store = StateStore(root / "state.sqlite3")
        self.delivery = FakeDelivery(root / "artifacts")
        self.delivery.root.mkdir()
        self.processor = TopicProcessor(
            state=self.store,
            runtime=FakeRuntime(),
            delivery=self.delivery,
            allowed_chat_ids=frozenset({"chat-a"}),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def event(event_id: str) -> IncomingEvent:
        return IncomingEvent(
            event_id,
            f"message-for-{event_id}",
            "chat-a",
            "topic-a",
            "user-a",
            "hello",
        )

    def test_pipeline_persists_before_delivery_and_deduplicates(self) -> None:
        self.assertEqual(self.processor.process(self.event("event-a")), "completed")
        self.assertEqual(self.processor.process(self.event("event-a")), "duplicate")
        self.assertEqual(len(self.delivery.delivered), 1)
        self.assertEqual(self.store.get_turn("event-a").status, "completed")

    def test_queued_turn_can_resume_after_earlier_terminal(self) -> None:
        self.store.claim_event("event-a", "message-for-event-a", "topic-a")
        self.assertEqual(self.processor.process(self.event("event-b")), "queued")
        self.store.transition("event-a", "failed_visible")
        self.assertEqual(self.processor.process(self.event("event-b")), "completed")


if __name__ == "__main__":
    unittest.main()
