from django.test import SimpleTestCase, override_settings

from scheduler.crontab import (
    cron_comment_matches_namespace,
    format_scheduler_cron_comment,
    scheduled_workflow_redis_lock_key,
)


@override_settings(SCHEDULER_NAMESPACE="prod")
class SchedulerNamespaceHelpersTests(SimpleTestCase):
    def test_format_comment_includes_ns_and_sw_id(self):
        self.assertEqual(
            format_scheduler_cron_comment(42, namespace="staging"),
            "# lango_core scheduler ns=staging sw_id=42",
        )

    def test_lock_key_includes_namespace(self):
        self.assertEqual(
            scheduled_workflow_redis_lock_key(7, namespace="staging"),
            "workflow_lock:staging:sw:7",
        )

    def test_cron_comment_matches_only_same_namespace(self):
        c = "# lango_core scheduler ns=prod sw_id=1"
        self.assertTrue(cron_comment_matches_namespace(c, "prod"))
        self.assertFalse(cron_comment_matches_namespace(c, "staging"))

    def test_legacy_comment_without_ns_never_matches(self):
        c = "# lango_core scheduler sw_id=1"
        self.assertFalse(cron_comment_matches_namespace(c, "prod"))
