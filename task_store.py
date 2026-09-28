"""Local SQLite storage for 每日任务本. No third-party packages required."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path


DIFFICULTIES = ("简单", "普通", "困难")
DEFAULT_REWARDS = {"简单": 5, "普通": 10, "困难": 20}


def default_data_dir() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / "每日任务本"


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_data_dir() / "tasks.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self._init_schema()
        self.archive_previous_days()

    def close(self):
        self.db.close()

    def _init_schema(self):
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    completed_at TEXT,
                    earned_coins INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_date);
                CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed_at);
                CREATE TABLE IF NOT EXISTS shop (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    cost INTEGER NOT NULL CHECK(cost > 0),
                    description TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS redemptions (
                    id INTEGER PRIMARY KEY,
                    item_name TEXT NOT NULL,
                    cost INTEGER NOT NULL CHECK(cost > 0),
                    redeemed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            task_columns = {row[1] for row in self.db.execute("PRAGMA table_info(tasks)")}
            if "archived" not in task_columns:
                self.db.execute("ALTER TABLE tasks ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
            redemption_columns = {row[1] for row in self.db.execute("PRAGMA table_info(redemptions)")}
            if "item_id" not in redemption_columns:
                self.db.execute("ALTER TABLE redemptions ADD COLUMN item_id INTEGER")
            # Older databases stored only the reward name. Match unambiguous names.
            self.db.execute("""
                UPDATE redemptions
                SET item_id = (SELECT MIN(id) FROM shop WHERE name = redemptions.item_name)
                WHERE item_id IS NULL
                  AND (SELECT COUNT(*) FROM shop WHERE name = redemptions.item_name) = 1
            """)
            for difficulty, coins in DEFAULT_REWARDS.items():
                self.db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (f"reward_{difficulty}", str(coins)))
            self.db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme','浅色')")
            self.db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('background','')")
            self.db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('debt_limit',?)", (str(max(100, -self.balance())),))

    def archive_previous_days(self, today: date | None = None) -> int:
        cutoff = (today or date.today()).isoformat()
        with self.db:
            return self.db.execute(
                "UPDATE tasks SET archived=1 WHERE archived=0 AND completed_at IS NOT NULL AND substr(completed_at,1,10) < ?",
                (cutoff,),
            ).rowcount

    def debt_limit(self) -> int:
        return int(self.setting("debt_limit", "100"))

    def set_debt_limit(self, limit: int):
        if not 0 <= limit <= 100000:
            raise ValueError("负金币额度请输入 0 到 100000 的整数。")
        if self.balance() < -limit:
            raise ValueError("当前欠币已超过这个额度，请先赚回金币或设置更大的额度。")
        self.set_setting("debt_limit", str(limit))

    def factory_reset(self):
        with self.db:
            for table in ("redemptions", "shop", "tasks", "settings"):
                self.db.execute(f"DELETE FROM {table}")
            defaults = {"theme": "海蓝", "background": "", "debt_limit": "100"}
            defaults.update({f"reward_{name}": str(coins) for name, coins in DEFAULT_REWARDS.items()})
            self.db.executemany("INSERT INTO settings(key,value) VALUES(?,?)", defaults.items())

    def setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self.db:
            self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def rewards(self) -> dict[str, int]:
        return {name: int(self.setting(f"reward_{name}", str(DEFAULT_REWARDS[name]))) for name in DIFFICULTIES}

    def tasks_for_day(self, day: str):
        return self.db.execute("SELECT * FROM tasks WHERE due_date=? AND archived=0 ORDER BY completed_at IS NOT NULL, id DESC", (day,)).fetchall()

    def tasks(self):
        return self.db.execute("SELECT * FROM tasks WHERE archived=0 ORDER BY completed_at IS NOT NULL, due_date DESC, id DESC").fetchall()

    def completed_on(self, day: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM tasks WHERE substr(completed_at,1,10)=?", (day,)
        ).fetchone()[0]

    def task(self, task_id: int):
        return self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()

    def categories(self) -> list[str]:
        rows = self.db.execute("SELECT DISTINCT category FROM tasks WHERE archived=0 ORDER BY category").fetchall()
        return list(dict.fromkeys(["日常", "工作", "学习", "兴趣"] + [row[0] for row in rows]))

    def add_task(self, title: str, category: str, difficulty: str, due_date: str, notes: str = "") -> int:
        self._validate_task(title, category, difficulty, due_date)
        with self.db:
            cur = self.db.execute(
                "INSERT INTO tasks(title,category,difficulty,due_date,notes,created_at) VALUES(?,?,?,?,?,?)",
                (title.strip(), category.strip(), difficulty, due_date, notes.strip(), datetime.now().isoformat(timespec="seconds")),
            )
            return cur.lastrowid

    def edit_task(self, task_id: int, title: str, category: str, difficulty: str, due_date: str, notes: str = ""):
        self._validate_task(title, category, difficulty, due_date)
        with self.db:
            self.db.execute(
                "UPDATE tasks SET title=?,category=?,difficulty=?,due_date=?,notes=? WHERE id=?",
                (title.strip(), category.strip(), difficulty, due_date, notes.strip(), task_id),
            )

    @staticmethod
    def _validate_task(title: str, category: str, difficulty: str, due_date: str):
        if not title.strip() or not category.strip():
            raise ValueError("任务名称和分类不能为空。")
        if difficulty not in DIFFICULTIES:
            raise ValueError("请选择有效的难度。")
        try:
            if date.fromisoformat(due_date).isoformat() != due_date:
                raise ValueError
        except ValueError:
            raise ValueError("日期请填写为 YYYY-MM-DD。") from None

    def delete_task(self, task_id: int):
        with self.db:
            task = self.task(task_id)
            if task and task["completed_at"] is not None:
                # Keep completion history as the source of earned coins and calendar stats.
                self.db.execute("UPDATE tasks SET archived=1 WHERE id=?", (task_id,))
            else:
                self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def set_completed(self, task_id: int, completed: bool, when: datetime | None = None) -> int:
        with self.db:
            task = self.task(task_id)
            if task is None:
                raise ValueError("任务不存在。")
            if completed and task["completed_at"] is None:
                coins = self.rewards()[task["difficulty"]]
                now = (when or datetime.now()).isoformat(timespec="seconds")
                self.db.execute("UPDATE tasks SET completed_at=?,earned_coins=? WHERE id=?", (now, coins, task_id))
                return coins
            if not completed and task["completed_at"] is not None:
                coins = task["earned_coins"]
                if self.balance() - coins < -self.debt_limit():
                    raise ValueError("撤销后余额会超过负金币额度，请先赚回金币或调高额度。")
                self.db.execute("UPDATE tasks SET completed_at=NULL,earned_coins=0 WHERE id=?", (task_id,))
                return -coins
        return 0

    def balance(self) -> int:
        earned = self.db.execute("SELECT COALESCE(SUM(earned_coins),0) FROM tasks WHERE completed_at IS NOT NULL").fetchone()[0]
        spent = self.db.execute("SELECT COALESCE(SUM(cost),0) FROM redemptions").fetchone()[0]
        return earned - spent

    def add_item(self, name: str, cost: int, description: str = "") -> int:
        if not name.strip() or cost <= 0:
            raise ValueError("商品名称不能为空，价格须大于 0。")
        with self.db:
            cur = self.db.execute("INSERT INTO shop(name,cost,description) VALUES(?,?,?)", (name.strip(), cost, description.strip()))
            return cur.lastrowid

    def items(self):
        return self.db.execute("SELECT * FROM shop WHERE active=1 ORDER BY id DESC").fetchall()

    def edit_item(self, item_id: int, name: str, cost: int, description: str = ""):
        if not name.strip() or cost <= 0:
            raise ValueError("商品名称不能为空，价格须大于 0。")
        with self.db:
            self.db.execute(
                "UPDATE shop SET name=?,cost=?,description=? WHERE id=? AND active=1",
                (name.strip(), cost, description.strip(), item_id),
            )

    def remove_item(self, item_id: int):
        with self.db:
            self.db.execute("UPDATE shop SET active=0 WHERE id=?", (item_id,))

    def redeem(self, item_id: int, when: datetime | None = None):
        with self.db:
            item = self.db.execute("SELECT * FROM shop WHERE id=? AND active=1", (item_id,)).fetchone()
            if item is None:
                raise ValueError("商品不存在。")
            if self.balance() - item["cost"] < -self.debt_limit():
                raise ValueError(f"兑换后余额不能低于 −{self.debt_limit()} 金币。可在个性设置中调整额度。")
            self.db.execute(
                "INSERT INTO redemptions(item_name,cost,redeemed_at,item_id) VALUES(?,?,?,?)",
                (item["name"], item["cost"], (when or datetime.now()).isoformat(timespec="seconds"), item_id),
            )

    def redemptions(self, limit: int = 30):
        return self.db.execute("SELECT * FROM redemptions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def redemption_count(self, item_name: str | None = None, item_id: int | None = None) -> int:
        if item_name is None and item_id is None:
            return self.db.execute("SELECT COUNT(*) FROM redemptions").fetchone()[0]
        if item_id is not None:
            return self.db.execute(
                "SELECT COUNT(*) FROM redemptions WHERE item_id=? OR (item_id IS NULL AND item_name=?)",
                (item_id, item_name or ""),
            ).fetchone()[0]
        return self.db.execute("SELECT COUNT(*) FROM redemptions WHERE item_name=?", (item_name,)).fetchone()[0]

    def daily_stats(self, year: int) -> dict[str, tuple[int, int]]:
        rows = self.db.execute(
            "SELECT substr(completed_at,1,10) AS day, COUNT(*) AS count, SUM(earned_coins) AS coins "
            "FROM tasks WHERE completed_at >= ? AND completed_at < ? GROUP BY day",
            (f"{year:04d}-01-01", f"{year+1:04d}-01-01"),
        ).fetchall()
        return {r["day"]: (r["count"], r["coins"]) for r in rows}

    def yearly_stats(self) -> list[tuple[int, int, int]]:
        rows = self.db.execute(
            "SELECT CAST(substr(completed_at,1,4) AS INTEGER) AS year, COUNT(*) AS count, SUM(earned_coins) AS coins "
            "FROM tasks WHERE completed_at IS NOT NULL GROUP BY year ORDER BY year DESC"
        ).fetchall()
        return [(r["year"], r["count"], r["coins"]) for r in rows]
