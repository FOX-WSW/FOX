from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from __PACKAGE_NAME__.state import StateStore


class StateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.temporary.name) / "state.sqlite3")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_topic_binding_and_event_idempotency(self) -> None:
        self.store.bind_topic("topic-a", "thread-a")
        self.assertEqual(self.store.thread_for_topic("topic-a"), "thread-a")
        self.assertTrue(self.store.claim_event("event-a", "message-a", "topic-a"))
        self.assertFalse(self.store.claim_event("event-a", "message-a", "topic-a"))

    def test_message_id_deduplicates_different_event_ids(self) -> None:
        self.assertTrue(self.store.claim_event("event-a", "message-a", "topic-a"))
        self.assertFalse(self.store.claim_event("event-b", "message-a", "topic-a"))
        self.assertEqual(self.store.get_turn_by_message("message-a").event_id, "event-a")

    def test_answer_must_be_persisted_before_delivery(self) -> None:
        self.store.claim_event("event-a", "message-a", "topic-a")
        self.store.transition("event-a", "running")
        with self.assertRaisesRegex(ValueError, "answer_path"):
            self.store.transition("event-a", "answer_persisted")
        self.store.transition(
            "event-a",
            "answer_persisted",
            answer_path="artifacts/event-a.md",
        )
        self.store.transition("event-a", "delivery_pending")
        self.store.transition(
            "event-a",
            "delivered",
            external_message_id="reply-a",
        )
        self.store.transition("event-a", "completed")
        turn = self.store.get_turn("event-a")
        self.assertIsNotNone(turn)
        self.assertEqual(turn.status, "completed")

    def test_invalid_transition_is_rejected(self) -> None:
        self.store.claim_event("event-a", "message-a", "topic-a")
        with self.assertRaisesRegex(ValueError, "invalid state transition"):
            self.store.transition("event-a", "completed")

    def test_topic_fifo_blocks_later_turn_until_terminal(self) -> None:
        self.store.claim_event("event-a", "message-a", "topic-a")
        self.store.claim_event("event-b", "message-b", "topic-a")
        self.assertTrue(self.store.can_start("event-a"))
        self.assertFalse(self.store.can_start("event-b"))
        self.store.transition("event-a", "failed_visible")
        self.assertTrue(self.store.can_start("event-b"))

    def test_retry_is_due_only_after_its_schedule(self) -> None:
        self.store.claim_event("event-a", "message-a", "topic-a")
        self.store.transition("event-a", "running")
        self.store.schedule_retry(
            "event-a",
            error_code="timeout",
            delay_seconds=60,
        )
        self.assertFalse(self.store.can_start("event-a"))
        self.assertNotIn("event-a", self.store.ready_event_ids())
        turn = self.store.get_turn("event-a")
        self.assertEqual(turn.status, "retry_pending")
        self.assertEqual(turn.attempt_count, 1)

    def test_ready_queue_returns_one_fifo_head_per_topic(self) -> None:
        self.store.claim_event("event-a", "message-a", "topic-a")
        self.store.claim_event("event-b", "message-b", "topic-a")
        self.store.claim_event("event-c", "message-c", "topic-b")
        self.assertEqual(self.store.ready_event_ids(), ["event-a", "event-c"])

    def test_run_claim_is_atomic(self) -> None:
        self.store.claim_event("event-a", "message-a", "topic-a")
        self.assertTrue(
            self.store.claim_for_run("event-a", worker_id="worker-a")
        )
        self.assertFalse(
            self.store.claim_for_run("event-a", worker_id="worker-b")
        )
        self.assertEqual(self.store.get_turn("event-a").status, "running")

    def test_expired_worker_lease_returns_to_retry_queue(self) -> None:
        self.store.claim_event("event-a", "message-a", "topic-a")
        self.store.claim_for_run("event-a", worker_id="worker-a", lease_seconds=1)
        time.sleep(1.1)
        self.assertEqual(self.store.recover_expired_leases(), 1)
        self.assertEqual(self.store.get_turn("event-a").status, "retry_pending")
        self.assertIn("event-a", self.store.ready_event_ids())

    def test_stale_worker_is_fenced_after_lease_recovery(self) -> None:
        self.store.claim_event("event-a", "message-a", "topic-a")
        old_token = self.store.claim_for_run(
            "event-a",
            worker_id="worker-a",
            lease_seconds=1,
        )
        time.sleep(1.1)
        self.store.recover_expired_leases()
        new_token = self.store.claim_for_run("event-a", worker_id="worker-b")
        self.assertNotEqual(old_token, new_token)
        with self.assertRaisesRegex(ValueError, "fencing token"):
            self.store.transition(
                "event-a",
                "answer_persisted",
                answer_path="stale.txt",
                worker_id="worker-a",
                lease_token=old_token,
            )
        self.store.transition(
            "event-a",
            "answer_persisted",
            answer_path="current.txt",
            worker_id="worker-b",
            lease_token=new_token,
        )


if __name__ == "__main__":
    unittest.main()
