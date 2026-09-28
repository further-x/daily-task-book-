"""Regression checks for daily cleanup, coin debt and factory reset."""
import unittest
import uuid
from datetime import date, datetime
from pathlib import Path

from task_store import Store


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).parent / "feature_test_data" / f"{uuid.uuid4()}.db"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()

    def test_cleanup_keeps_completion_timestamp_and_stats(self):
        s = self.store
        task = s.add_task("Past scheduled task", "学习", "困难", "2025-12-30")
        s.set_completed(task, True, datetime(2026, 9, 27, 23, 59, 59))
        self.assertEqual(s.archive_previous_days(date(2026, 9, 27)), 0)
        self.assertEqual(len(s.tasks()), 1)
        self.assertEqual(s.archive_previous_days(date(2026, 9, 28)), 1)
        self.assertEqual(s.tasks(), [])
        self.assertEqual(s.balance(), 20)
        self.assertEqual(s.daily_stats(2026), {"2026-09-27": (1, 20)})
        self.assertEqual(s.task(task)["completed_at"], "2026-09-27T23:59:59")

    def test_debt_boundary_rejects_without_new_redemption(self):
        s = self.store
        s.set_debt_limit(10)
        item = s.add_item("Reward", 10)
        s.redeem(item)
        self.assertEqual(s.balance(), -10)
        with self.assertRaises(ValueError):
            s.redeem(item)
        self.assertEqual(s.redemption_count(), 1)
        with self.assertRaises(ValueError):
            s.set_debt_limit(9)
        self.assertEqual(s.debt_limit(), 10)

    def test_undo_obeys_debt_limit(self):
        s = self.store
        s.set_debt_limit(0)
        task = s.add_task("Task", "日常", "简单", date.today().isoformat())
        s.set_completed(task, True)
        s.redeem(s.add_item("Reward", 5))
        with self.assertRaises(ValueError):
            s.set_completed(task, False)
        self.assertIsNotNone(s.task(task)["completed_at"])
        s.set_debt_limit(5)
        s.set_completed(task, False)
        self.assertEqual(s.balance(), -5)

    def test_factory_reset_clears_archived_and_restores_defaults(self):
        s = self.store
        task = s.add_task("Task", "工作", "困难", date.today().isoformat())
        s.set_completed(task, True)
        s.delete_task(task)
        s.redeem(s.add_item("Reward", 10))
        s.set_setting("theme", "深夜")
        s.set_setting("reward_简单", "999")
        s.factory_reset()
        self.assertIsNone(s.task(task))
        self.assertEqual(s.balance(), 0)
        self.assertEqual(s.redemption_count(), 0)
        self.assertEqual(s.items(), [])
        self.assertEqual(s.daily_stats(date.today().year), {})
        self.assertEqual(s.setting("theme"), "海蓝")
        self.assertEqual(s.rewards(), {"简单": 5, "普通": 10, "困难": 20})
        self.assertEqual(s.debt_limit(), 100)


if __name__ == "__main__":
    unittest.main()
