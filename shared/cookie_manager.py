"""Pinterest Cookie管理器

借鉴 social-auto-upload-main 的认证模式：
- 使用 Playwright storage_state 保存完整浏览器状态（cookies + localStorage）
- SQLite 数据库存储 cookie 记录，每个 worker 分配一个独立 cookie
- Cookie 验证：加载 storage_state 后访问 Pinterest，检测是否需要登录
- 登录流程：弹出可见浏览器 → 等待用户登录 → 保存 storage_state → 更新数据库
"""

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

DB_DIR = Path(__file__).parent.parent / "db"
COOKIES_DIR = Path(__file__).parent.parent / "cookiesFile"


class CookieManager:
    """Pinterest Cookie 数据库管理器

    数据库表 pinterest_accounts:
        id          - 自增主键
        file_path   - storage_state JSON 文件路径
        label       - 账号标签（如 worker-0, worker-1）
        status      - 状态: 1=有效, 0=失效, -1=待登录
        last_check  - 最后验证时间
        created_at  - 创建时间
        worker_id   - 当前分配的 worker_id（NULL=未分配）
    """

    def __init__(self, db_path: str = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            DB_DIR.mkdir(parents=True, exist_ok=True)
            self.db_path = DB_DIR / "pinterest_cookies.db"

        COOKIES_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pinterest_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    label TEXT DEFAULT '',
                    status INTEGER DEFAULT -1,
                    last_check TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    worker_id TEXT
                )
            """)
            conn.commit()

    def add_account(self, storage_state: dict = None, label: str = "") -> int:
        """添加一个新账号记录

        Args:
            storage_state: Playwright storage_state 字典，为空则创建待登录记录
            label: 账号标签

        Returns:
            新记录的 id
        """
        file_name = f"{uuid.uuid1()}.json"
        file_path = COOKIES_DIR / file_name

        if storage_state:
            file_path.write_text(json.dumps(storage_state, ensure_ascii=False), encoding="utf-8")
            status = 1
        else:
            file_path.write_text("{}", encoding="utf-8")
            status = -1

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO pinterest_accounts (file_path, label, status) VALUES (?, ?, ?)",
                (file_name, label, status),
            )
            conn.commit()
            return cursor.lastrowid

    def get_account_for_worker(self, worker_id: str) -> Optional[Dict]:
        """为指定 worker 获取一个可用的 cookie 账号

        优先级：
        1. 已分配给该 worker 且有效的账号
        2. 未分配的有效账号
        3. 已分配但需重新验证的账号

        Args:
            worker_id: Worker 标识

        Returns:
            账号信息字典，包含 id, file_path, label, status, full_path
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM pinterest_accounts WHERE worker_id = ? AND status = 1 ORDER BY id LIMIT 1",
                (worker_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)

            cursor.execute(
                "SELECT * FROM pinterest_accounts WHERE worker_id IS NULL AND status = 1 ORDER BY id LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE pinterest_accounts SET worker_id = ? WHERE id = ?",
                    (worker_id, row["id"]),
                )
                conn.commit()
                return self._row_to_dict(row)

            cursor.execute(
                "SELECT * FROM pinterest_accounts WHERE worker_id = ? ORDER BY id LIMIT 1",
                (worker_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)

            cursor.execute(
                "SELECT * FROM pinterest_accounts WHERE worker_id IS NULL ORDER BY id LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE pinterest_accounts SET worker_id = ? WHERE id = ?",
                    (worker_id, row["id"]),
                )
                conn.commit()
                return self._row_to_dict(row)

        return None

    def update_storage_state(self, account_id: int, storage_state: dict):
        """更新账号的 storage_state 文件

        Args:
            account_id: 账号 ID
            storage_state: 新的 storage_state 字典
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM pinterest_accounts WHERE id = ?", (account_id,))
            row = cursor.fetchone()
            if not row:
                return

            file_path = COOKIES_DIR / row["file_path"]
            file_path.write_text(json.dumps(storage_state, ensure_ascii=False), encoding="utf-8")

            cursor.execute(
                "UPDATE pinterest_accounts SET status = 1, last_check = ? WHERE id = ?",
                (datetime.now().isoformat(), account_id),
            )
            conn.commit()

    def set_status(self, account_id: int, status: int):
        """设置账号状态

        Args:
            account_id: 账号 ID
            status: 状态值 (1=有效, 0=失效, -1=待登录)
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE pinterest_accounts SET status = ?, last_check = ? WHERE id = ?",
                (status, datetime.now().isoformat(), account_id),
            )
            conn.commit()

    def release_worker(self, worker_id: str):
        """释放 worker 占用的账号（worker 结束时调用）

        Args:
            worker_id: Worker 标识
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE pinterest_accounts SET worker_id = NULL WHERE worker_id = ?",
                (worker_id,),
            )
            conn.commit()

    def get_all_accounts(self) -> List[Dict]:
        """获取所有账号记录"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pinterest_accounts ORDER BY id")
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def delete_account(self, account_id: int) -> bool:
        """删除账号记录及对应的 cookie 文件

        Args:
            account_id: 账号 ID

        Returns:
            是否成功删除
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM pinterest_accounts WHERE id = ?", (account_id,))
            row = cursor.fetchone()
            if not row:
                return False

            cookie_file = COOKIES_DIR / row["file_path"]
            if cookie_file.exists():
                try:
                    cookie_file.unlink()
                except Exception:
                    pass

            cursor.execute("DELETE FROM pinterest_accounts WHERE id = ?", (account_id,))
            conn.commit()
            return True

    def load_storage_state(self, account_id: int) -> Optional[dict]:
        """加载指定账号的 storage_state

        Args:
            account_id: 账号 ID

        Returns:
            storage_state 字典，文件不存在或为空返回 None
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM pinterest_accounts WHERE id = ?", (account_id,))
            row = cursor.fetchone()
            if not row:
                return None

            file_path = COOKIES_DIR / row["file_path"]
            if not file_path.exists():
                return None

            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if not data or not data.get("cookies"):
                    return None
                return data
            except (json.JSONDecodeError, Exception):
                return None

    def ensure_accounts_for_workers(self, num_workers: int) -> List[Dict]:
        """确保数据库中有足够的账号供所有 worker 使用

        如果现有有效账号不足，自动创建待登录的占位记录。

        Args:
            num_workers: 需要的 worker 数量

        Returns:
            所有可用账号列表
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM pinterest_accounts WHERE status = 1")
            valid_count = cursor.fetchone()["cnt"]

            need_create = max(0, num_workers - valid_count)
            for i in range(need_create):
                label = f"auto_{uuid.uuid4().hex[:8]}"
                self.add_account(label=label)

            if need_create > 0:
                print(f"[CookieManager] 自动创建了 {need_create} 个待登录账号")

        return self.get_all_accounts()

    def _row_to_dict(self, row) -> Dict:
        d = dict(row)
        d["full_path"] = str(COOKIES_DIR / row["file_path"])
        return d
