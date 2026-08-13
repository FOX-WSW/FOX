from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from __PACKAGE_NAME__.approvals import ApprovalDenied, ApprovalStore
from __PACKAGE_NAME__.policy import CapabilityRequest


class ApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ApprovalStore(Path(self.temporary.name) / "state.sqlite3")
        self.request = CapabilityRequest("publish_document", "uat", {"document_id": "doc-a"})

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_and_approve(self) -> str:
        approval_id = self.store.request(
            requester_id="requester-a",
            approver_id="approver-a",
            topic_id="topic-a",
            capability=self.request.name,
            environment=self.request.environment,
            operation_hash=self.request.operation_hash(),
        )
        self.store.approve(approval_id, actor_id="approver-a")
        return approval_id

    def test_exact_approval_is_consumed_once(self) -> None:
        approval_id = self.create_and_approve()
        approval = self.store.consume(
            approval_id,
            requester_id="requester-a",
            topic_id="topic-a",
            capability=self.request.name,
            environment=self.request.environment,
            operation_hash=self.request.operation_hash(),
        )
        self.assertEqual(approval.status, "consumed")
        with self.assertRaises(ApprovalDenied):
            self.store.consume(
                approval_id,
                requester_id="requester-a",
                topic_id="topic-a",
                capability=self.request.name,
                environment=self.request.environment,
                operation_hash=self.request.operation_hash(),
            )

    def test_parameter_change_does_not_consume_approval(self) -> None:
        approval_id = self.create_and_approve()
        changed = CapabilityRequest("publish_document", "prod", {"document_id": "doc-a"})
        with self.assertRaisesRegex(ApprovalDenied, "mismatch"):
            self.store.consume(
                approval_id,
                requester_id="requester-a",
                topic_id="topic-a",
                capability=changed.name,
                environment=changed.environment,
                operation_hash=changed.operation_hash(),
            )

    def test_only_bound_approver_can_approve(self) -> None:
        approval_id = self.store.request(
            requester_id="requester-a",
            approver_id="approver-a",
            topic_id="topic-a",
            capability=self.request.name,
            environment=self.request.environment,
            operation_hash=self.request.operation_hash(),
        )
        with self.assertRaisesRegex(ApprovalDenied, "bound approver"):
            self.store.approve(approval_id, actor_id="other-user")

    def test_expiry_is_persisted_for_audit(self) -> None:
        approval_id = self.store.request(
            requester_id="requester-a",
            approver_id="approver-a",
            topic_id="topic-a",
            capability=self.request.name,
            environment=self.request.environment,
            operation_hash=self.request.operation_hash(),
            ttl_seconds=1,
        )
        self.store.approve(approval_id, actor_id="approver-a")
        time.sleep(1.1)
        with self.assertRaisesRegex(ApprovalDenied, "expired"):
            self.store.consume(
                approval_id,
                requester_id="requester-a",
                topic_id="topic-a",
                capability=self.request.name,
                environment=self.request.environment,
                operation_hash=self.request.operation_hash(),
            )
        self.assertEqual(self.store.status(approval_id), "expired")


if __name__ == "__main__":
    unittest.main()
