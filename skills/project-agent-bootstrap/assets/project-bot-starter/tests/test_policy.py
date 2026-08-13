from __future__ import annotations

import unittest

from __PACKAGE_NAME__.policy import (
    CapabilityRequest,
    PolicyDenied,
    require_allowed_chat,
    validate_readonly_sql,
)


class PolicyTests(unittest.TestCase):
    def test_select_and_cte_are_allowed(self) -> None:
        self.assertEqual(validate_readonly_sql("select 1 from dual;"), "select 1 from dual")
        self.assertEqual(
            validate_readonly_sql("with x as (select 1 n) select n from x"),
            "with x as (select 1 n) select n from x",
        )

    def test_write_lock_and_side_effect_packages_are_denied(self) -> None:
        rejected = (
            "delete from jobs",
            "select * from jobs for update",
            "select utl_http.request('https://example.invalid') from dual",
            "select dbms_scheduler.generate_job_name from dual",
            "select 1 from dual; select 2 from dual",
        )
        for sql in rejected:
            with self.subTest(sql=sql), self.assertRaises(PolicyDenied):
                validate_readonly_sql(sql)

    def test_keywords_inside_literals_do_not_trigger(self) -> None:
        self.assertEqual(
            validate_readonly_sql("select 'delete; utl_http' as note from dual"),
            "select 'delete; utl_http' as note from dual",
        )

    def test_allowlist_fails_closed(self) -> None:
        with self.assertRaises(PolicyDenied):
            require_allowed_chat("chat-a", frozenset())
        require_allowed_chat("chat-a", frozenset({"chat-a"}))

    def test_operation_hash_is_stable(self) -> None:
        first = CapabilityRequest("deliver", "uat", {"b": 2, "a": 1})
        second = CapabilityRequest("deliver", "uat", {"a": 1, "b": 2})
        self.assertEqual(first.operation_hash(), second.operation_hash())


if __name__ == "__main__":
    unittest.main()
