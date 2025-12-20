"""锁机制测试。"""

import json
import pytest
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from cc_spec.core.lock import LockInfo, LockManager


class TestLockInfo:
    """测试 LockInfo 数据类。"""

    def test_create_lock_info(self):
        """测试创建 LockInfo 实例。"""
        lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-abc123",
            started_at=datetime.now(),
            timeout_minutes=30,
        )

        assert lock.task_id == "01-SETUP"
        assert lock.agent_id == "agent-abc123"
        assert lock.timeout_minutes == 30
        assert lock.hostname != ""  # 自动填充

    def test_is_expired_not_expired(self):
        """测试未过期的锁。"""
        lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-abc123",
            started_at=datetime.now(),
            timeout_minutes=30,
        )

        assert lock.is_expired() is False

    def test_is_expired_expired(self):
        """测试已过期的锁。"""
        lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-abc123",
            started_at=datetime.now() - timedelta(minutes=31),
            timeout_minutes=30,
        )

        assert lock.is_expired() is True

    def test_remaining_seconds(self):
        """测试剩余时间计算。"""
        lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-abc123",
            started_at=datetime.now(),
            timeout_minutes=1,  # 1 分钟
        )

        remaining = lock.remaining_seconds()
        assert 50 <= remaining <= 60  # 应该在 50-60 秒之间

    def test_remaining_seconds_expired(self):
        """测试已过期锁的剩余时间。"""
        lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-abc123",
            started_at=datetime.now() - timedelta(minutes=31),
            timeout_minutes=30,
        )

        assert lock.remaining_seconds() == 0

    def test_to_json(self):
        """测试序列化为 JSON。"""
        now = datetime.now()
        lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-abc123",
            started_at=now,
            timeout_minutes=30,
            hostname="test-host",
        )

        json_str = lock.to_json()
        data = json.loads(json_str)

        assert data["task_id"] == "01-SETUP"
        assert data["agent_id"] == "agent-abc123"
        assert data["timeout_minutes"] == 30
        assert data["hostname"] == "test-host"
        assert "started_at" in data

    def test_from_json(self):
        """测试从 JSON 反序列化。"""
        now = datetime.now()
        original = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-abc123",
            started_at=now,
            timeout_minutes=30,
            hostname="test-host",
        )

        json_str = original.to_json()
        restored = LockInfo.from_json(json_str)

        assert restored.task_id == original.task_id
        assert restored.agent_id == original.agent_id
        assert restored.timeout_minutes == original.timeout_minutes
        assert restored.hostname == original.hostname

    def test_to_dict(self):
        """测试转换为字典。"""
        lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-abc123",
            started_at=datetime.now(),
            timeout_minutes=30,
        )

        data = lock.to_dict()

        assert isinstance(data, dict)
        assert data["task_id"] == "01-SETUP"

    def test_from_dict(self):
        """测试从字典创建。"""
        data = {
            "task_id": "01-SETUP",
            "agent_id": "agent-abc123",
            "started_at": datetime.now().isoformat(),
            "timeout_minutes": 30,
            "hostname": "test-host",
        }

        lock = LockInfo.from_dict(data)

        assert lock.task_id == "01-SETUP"
        assert lock.agent_id == "agent-abc123"


class TestLockManager:
    """测试 LockManager 类。"""

    @pytest.fixture
    def temp_cc_spec_root(self, tmp_path: Path) -> Path:
        """创建临时 .cc-spec 目录。"""
        cc_spec_root = tmp_path / ".cc-spec"
        cc_spec_root.mkdir(parents=True, exist_ok=True)
        return cc_spec_root

    @pytest.fixture
    def lock_manager(self, temp_cc_spec_root: Path) -> LockManager:
        """创建 LockManager 实例。"""
        return LockManager(temp_cc_spec_root, timeout_minutes=30)

    def test_create_lock_manager(self, temp_cc_spec_root: Path):
        """测试创建 LockManager。"""
        manager = LockManager(temp_cc_spec_root, timeout_minutes=30)

        assert manager.locks_dir.exists()
        assert manager.default_timeout == 30

    def test_acquire_success(self, lock_manager: LockManager):
        """测试成功获取锁。"""
        result = lock_manager.acquire("01-SETUP", "agent-abc123")

        assert result is True

    def test_acquire_already_locked(self, lock_manager: LockManager):
        """测试锁被占用时获取失败。"""
        # 首次获取成功
        lock_manager.acquire("01-SETUP", "agent-abc123")

        # 其他 agent 尝试获取应失败
        result = lock_manager.acquire("01-SETUP", "agent-def456")

        assert result is False

    def test_acquire_same_agent(self, lock_manager: LockManager):
        """测试同一 agent 再次获取锁。"""
        # 首次获取
        lock_manager.acquire("01-SETUP", "agent-abc123")

        # 同一 agent 再次获取 (force=True)
        result = lock_manager.acquire("01-SETUP", "agent-abc123", force=True)

        assert result is True

    def test_acquire_expired_lock(self, lock_manager: LockManager, temp_cc_spec_root: Path):
        """测试获取已过期的锁。"""
        # 手动创建一个过期的锁
        lock_path = temp_cc_spec_root / "locks" / "01-SETUP.lock"
        expired_lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-old",
            started_at=datetime.now() - timedelta(minutes=31),
            timeout_minutes=30,
        )
        lock_path.write_text(expired_lock.to_json(), encoding="utf-8")

        # 新 agent 应该能获取锁
        result = lock_manager.acquire("01-SETUP", "agent-new")

        assert result is True

    def test_acquire_force(self, lock_manager: LockManager):
        """测试强制获取锁。"""
        # 首次获取
        lock_manager.acquire("01-SETUP", "agent-abc123")

        # 强制获取应成功
        result = lock_manager.acquire("01-SETUP", "agent-def456", force=True)

        assert result is True

    def test_acquire_custom_timeout(self, lock_manager: LockManager):
        """测试自定义超时时间。"""
        lock_manager.acquire("01-SETUP", "agent-abc123", timeout_minutes=60)

        info = lock_manager.get_lock_info("01-SETUP")
        assert info is not None
        assert info.timeout_minutes == 60

    def test_release_success(self, lock_manager: LockManager):
        """测试成功释放锁。"""
        lock_manager.acquire("01-SETUP", "agent-abc123")

        result = lock_manager.release("01-SETUP", "agent-abc123")

        assert result is True
        assert lock_manager.get_lock_info("01-SETUP") is None

    def test_release_nonexistent(self, lock_manager: LockManager):
        """测试释放不存在的锁。"""
        result = lock_manager.release("nonexistent-task", "agent-abc123")

        assert result is False

    def test_release_wrong_agent(self, lock_manager: LockManager):
        """测试错误 agent 释放锁。"""
        lock_manager.acquire("01-SETUP", "agent-abc123")

        # 其他 agent 尝试释放应失败
        result = lock_manager.release("01-SETUP", "agent-def456")

        assert result is False

    def test_release_without_agent_id(self, lock_manager: LockManager):
        """测试不指定 agent_id 释放锁。"""
        lock_manager.acquire("01-SETUP", "agent-abc123")

        # 不指定 agent_id 应成功
        result = lock_manager.release("01-SETUP")

        assert result is True

    def test_get_lock_info_exists(self, lock_manager: LockManager):
        """测试获取存在的锁信息。"""
        lock_manager.acquire("01-SETUP", "agent-abc123")

        info = lock_manager.get_lock_info("01-SETUP")

        assert info is not None
        assert info.task_id == "01-SETUP"
        assert info.agent_id == "agent-abc123"

    def test_get_lock_info_not_exists(self, lock_manager: LockManager):
        """测试获取不存在的锁信息。"""
        info = lock_manager.get_lock_info("nonexistent-task")

        assert info is None

    def test_is_locked_true(self, lock_manager: LockManager):
        """测试锁定状态检查 - 已锁定。"""
        lock_manager.acquire("01-SETUP", "agent-abc123")

        assert lock_manager.is_locked("01-SETUP") is True

    def test_is_locked_false(self, lock_manager: LockManager):
        """测试锁定状态检查 - 未锁定。"""
        assert lock_manager.is_locked("nonexistent-task") is False

    def test_is_locked_expired(self, lock_manager: LockManager, temp_cc_spec_root: Path):
        """测试锁定状态检查 - 已过期。"""
        # 手动创建过期锁
        lock_path = temp_cc_spec_root / "locks" / "01-SETUP.lock"
        expired_lock = LockInfo(
            task_id="01-SETUP",
            agent_id="agent-old",
            started_at=datetime.now() - timedelta(minutes=31),
            timeout_minutes=30,
        )
        lock_path.write_text(expired_lock.to_json(), encoding="utf-8")

        # 过期锁不算锁定
        assert lock_manager.is_locked("01-SETUP") is False

    def test_cleanup_expired_none(self, lock_manager: LockManager):
        """测试清理 - 无过期锁。"""
        lock_manager.acquire("01-SETUP", "agent-abc123")

        cleaned = lock_manager.cleanup_expired()

        assert len(cleaned) == 0

    def test_cleanup_expired_some(self, lock_manager: LockManager, temp_cc_spec_root: Path):
        """测试清理 - 有过期锁。"""
        # 创建一个过期锁
        lock_path = temp_cc_spec_root / "locks" / "old-task.lock"
        expired_lock = LockInfo(
            task_id="old-task",
            agent_id="agent-old",
            started_at=datetime.now() - timedelta(minutes=31),
            timeout_minutes=30,
        )
        lock_path.write_text(expired_lock.to_json(), encoding="utf-8")

        # 创建一个有效锁
        lock_manager.acquire("new-task", "agent-new")

        cleaned = lock_manager.cleanup_expired()

        assert "old-task" in cleaned
        assert len(cleaned) == 1
        assert lock_manager.is_locked("new-task") is True

    def test_list_locks_empty(self, lock_manager: LockManager):
        """测试列出锁 - 无锁。"""
        locks = lock_manager.list_locks()

        assert len(locks) == 0

    def test_list_locks_some(self, lock_manager: LockManager):
        """测试列出锁 - 有锁。"""
        lock_manager.acquire("01-SETUP", "agent-a")
        lock_manager.acquire("02-MODEL", "agent-b")

        locks = lock_manager.list_locks()

        assert len(locks) == 2
        task_ids = {lock.task_id for lock in locks}
        assert "01-SETUP" in task_ids
        assert "02-MODEL" in task_ids

    def test_list_locks_excludes_expired(self, lock_manager: LockManager, temp_cc_spec_root: Path):
        """测试列出锁 - 排除过期锁。"""
        # 创建过期锁
        lock_path = temp_cc_spec_root / "locks" / "expired.lock"
        expired_lock = LockInfo(
            task_id="expired",
            agent_id="agent-old",
            started_at=datetime.now() - timedelta(minutes=31),
            timeout_minutes=30,
        )
        lock_path.write_text(expired_lock.to_json(), encoding="utf-8")

        # 创建有效锁
        lock_manager.acquire("valid", "agent-new")

        locks = lock_manager.list_locks()

        assert len(locks) == 1
        assert locks[0].task_id == "valid"

    def test_force_release_all(self, lock_manager: LockManager):
        """测试强制释放所有锁。"""
        lock_manager.acquire("01-SETUP", "agent-a")
        lock_manager.acquire("02-MODEL", "agent-b")
        lock_manager.acquire("03-API", "agent-c")

        count = lock_manager.force_release_all()

        assert count == 3
        assert len(lock_manager.list_locks()) == 0


class TestLockManagerEdgeCases:
    """测试 LockManager 边界情况。"""

    @pytest.fixture
    def temp_cc_spec_root(self, tmp_path: Path) -> Path:
        """创建临时 .cc-spec 目录。"""
        cc_spec_root = tmp_path / ".cc-spec"
        cc_spec_root.mkdir(parents=True, exist_ok=True)
        return cc_spec_root

    def test_special_characters_in_task_id(self, temp_cc_spec_root: Path):
        """测试任务 ID 包含特殊字符。"""
        manager = LockManager(temp_cc_spec_root)

        # 包含特殊字符的任务 ID
        result = manager.acquire("task/with/slashes", "agent-abc")

        assert result is True

    def test_corrupted_lock_file(self, temp_cc_spec_root: Path):
        """测试损坏的锁文件。"""
        manager = LockManager(temp_cc_spec_root)

        # 创建损坏的锁文件
        lock_path = temp_cc_spec_root / "locks" / "corrupted.lock"
        lock_path.write_text("not valid json", encoding="utf-8")

        # 获取锁信息应返回 None
        info = manager.get_lock_info("corrupted")
        assert info is None

        # 应该能覆盖损坏的锁
        result = manager.acquire("corrupted", "agent-abc")
        assert result is True

    def test_cleanup_handles_corrupted_files(self, temp_cc_spec_root: Path):
        """测试清理损坏的锁文件。"""
        manager = LockManager(temp_cc_spec_root)

        # 创建损坏的锁文件
        lock_path = temp_cc_spec_root / "locks" / "corrupted.lock"
        lock_path.write_text("not valid json", encoding="utf-8")

        cleaned = manager.cleanup_expired()

        # 损坏的文件也应被清理
        assert "corrupted" in cleaned


class TestConcurrency:
    """测试并发场景。"""

    @pytest.fixture
    def temp_cc_spec_root(self, tmp_path: Path) -> Path:
        """创建临时 .cc-spec 目录。"""
        cc_spec_root = tmp_path / ".cc-spec"
        cc_spec_root.mkdir(parents=True, exist_ok=True)
        return cc_spec_root

    def test_multiple_managers_same_task(self, temp_cc_spec_root: Path):
        """测试多个 manager 实例操作同一任务。"""
        manager1 = LockManager(temp_cc_spec_root)
        manager2 = LockManager(temp_cc_spec_root)

        # manager1 获取锁
        result1 = manager1.acquire("shared-task", "agent-1")
        assert result1 is True

        # manager2 尝试获取应失败
        result2 = manager2.acquire("shared-task", "agent-2")
        assert result2 is False

        # manager1 释放后 manager2 应能获取
        manager1.release("shared-task", "agent-1")
        result3 = manager2.acquire("shared-task", "agent-2")
        assert result3 is True
