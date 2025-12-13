"""锁管理模块 (v1.3 新增)。

提供基于文件的分布式锁机制，防止多个实例同时执行同一任务。
锁文件存储在 .cc-spec/locks/ 目录下。
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class LockInfo:
    """锁信息数据类。

    存储任务锁的详细信息，包括持有者、开始时间、超时设置等。

    Attributes:
        task_id: 被锁定的任务 ID
        agent_id: 持有锁的 SubAgent ID
        started_at: 锁创建时间
        timeout_minutes: 锁超时时间 (分钟)
        hostname: 创建锁的机器标识
    """

    task_id: str
    agent_id: str
    started_at: datetime
    timeout_minutes: int = 30
    hostname: str = ""

    def __post_init__(self) -> None:
        """初始化时自动填充 hostname。"""
        if not self.hostname:
            try:
                self.hostname = socket.gethostname()
            except Exception:
                self.hostname = "unknown"

    def is_expired(self) -> bool:
        """检查锁是否已超时。

        Returns:
            True 如果锁已超时，False 否则
        """
        elapsed = datetime.now() - self.started_at
        return elapsed.total_seconds() > self.timeout_minutes * 60

    def remaining_seconds(self) -> float:
        """计算锁剩余有效时间 (秒)。

        Returns:
            剩余秒数，如果已超时则返回 0
        """
        elapsed = datetime.now() - self.started_at
        remaining = self.timeout_minutes * 60 - elapsed.total_seconds()
        return max(0, remaining)

    def to_json(self) -> str:
        """序列化为 JSON 字符串。

        Returns:
            JSON 格式的锁信息
        """
        return json.dumps({
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at.isoformat(),
            "timeout_minutes": self.timeout_minutes,
            "hostname": self.hostname,
        }, ensure_ascii=False, indent=2)

    def to_dict(self) -> dict:
        """转换为字典格式。

        Returns:
            字典格式的锁信息
        """
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at.isoformat(),
            "timeout_minutes": self.timeout_minutes,
            "hostname": self.hostname,
        }

    @classmethod
    def from_json(cls, data: str) -> LockInfo:
        """从 JSON 字符串反序列化。

        Args:
            data: JSON 格式的锁信息

        Returns:
            LockInfo 实例
        """
        obj = json.loads(data)
        return cls(
            task_id=obj["task_id"],
            agent_id=obj["agent_id"],
            started_at=datetime.fromisoformat(obj["started_at"]),
            timeout_minutes=obj.get("timeout_minutes", 30),
            hostname=obj.get("hostname", ""),
        )

    @classmethod
    def from_dict(cls, data: dict) -> LockInfo:
        """从字典创建实例。

        Args:
            data: 字典格式的锁信息

        Returns:
            LockInfo 实例
        """
        started_at = data["started_at"]
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        return cls(
            task_id=data["task_id"],
            agent_id=data["agent_id"],
            started_at=started_at,
            timeout_minutes=data.get("timeout_minutes", 30),
            hostname=data.get("hostname", ""),
        )


class LockManager:
    """锁管理器。

    管理任务锁的获取、释放和清理操作。
    锁文件以 JSON 格式存储在 .cc-spec/locks/<task-id>.lock 路径下。
    """

    def __init__(self, cc_spec_root: Path, timeout_minutes: int = 30):
        """初始化锁管理器。

        Args:
            cc_spec_root: .cc-spec 目录路径
            timeout_minutes: 默认锁超时时间 (分钟)
        """
        self.locks_dir = cc_spec_root / "locks"
        self.default_timeout = timeout_minutes
        # 确保 locks 目录存在
        self.locks_dir.mkdir(parents=True, exist_ok=True)

    def _get_lock_path(self, task_id: str) -> Path:
        """获取任务对应的锁文件路径。

        Args:
            task_id: 任务 ID

        Returns:
            锁文件路径
        """
        # 清理任务 ID 中的特殊字符
        safe_id = task_id.replace("/", "_").replace("\\", "_")
        return self.locks_dir / f"{safe_id}.lock"

    def acquire(
        self,
        task_id: str,
        agent_id: str,
        timeout_minutes: int | None = None,
        force: bool = False,
    ) -> bool:
        """尝试获取任务锁。

        Args:
            task_id: 任务 ID
            agent_id: 执行的 SubAgent ID
            timeout_minutes: 锁超时时间 (分钟)，None 使用默认值
            force: 是否强制获取 (覆盖已有锁)

        Returns:
            是否成功获取锁
        """
        lock_path = self._get_lock_path(task_id)
        timeout = timeout_minutes or self.default_timeout

        # 检查现有锁
        if lock_path.exists() and not force:
            try:
                existing = LockInfo.from_json(lock_path.read_text(encoding="utf-8"))
                if not existing.is_expired():
                    # 锁被占用且未超时
                    return False
            except (json.JSONDecodeError, KeyError):
                # 锁文件损坏，可以覆盖
                pass

        # 创建新锁
        lock_info = LockInfo(
            task_id=task_id,
            agent_id=agent_id,
            started_at=datetime.now(),
            timeout_minutes=timeout,
        )

        try:
            lock_path.write_text(lock_info.to_json(), encoding="utf-8")
            return True
        except OSError:
            return False

    def release(self, task_id: str, agent_id: str | None = None) -> bool:
        """释放任务锁。

        Args:
            task_id: 任务 ID
            agent_id: 可选，仅当锁属于该 agent 时才释放

        Returns:
            是否成功释放锁
        """
        lock_path = self._get_lock_path(task_id)

        if not lock_path.exists():
            return False

        # 如果指定了 agent_id，验证锁的所有权
        if agent_id:
            try:
                existing = LockInfo.from_json(lock_path.read_text(encoding="utf-8"))
                if existing.agent_id != agent_id:
                    # 锁不属于该 agent
                    return False
            except (json.JSONDecodeError, KeyError):
                pass

        try:
            lock_path.unlink()
            return True
        except OSError:
            return False

    def get_lock_info(self, task_id: str) -> LockInfo | None:
        """获取锁信息。

        Args:
            task_id: 任务 ID

        Returns:
            LockInfo 实例，如果锁不存在则返回 None
        """
        lock_path = self._get_lock_path(task_id)

        if not lock_path.exists():
            return None

        try:
            return LockInfo.from_json(lock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None

    def is_locked(self, task_id: str) -> bool:
        """检查任务是否被锁定。

        Args:
            task_id: 任务 ID

        Returns:
            True 如果任务被锁定且锁未超时
        """
        lock_info = self.get_lock_info(task_id)
        if lock_info is None:
            return False
        return not lock_info.is_expired()

    def cleanup_expired(self) -> list[str]:
        """清理所有过期的锁。

        Returns:
            被清理的任务 ID 列表
        """
        cleaned: list[str] = []

        if not self.locks_dir.exists():
            return cleaned

        for lock_file in self.locks_dir.glob("*.lock"):
            try:
                lock_info = LockInfo.from_json(lock_file.read_text(encoding="utf-8"))
                if lock_info.is_expired():
                    lock_file.unlink()
                    cleaned.append(lock_info.task_id)
            except (json.JSONDecodeError, KeyError, OSError):
                # 损坏的锁文件也清理掉
                try:
                    task_id = lock_file.stem
                    lock_file.unlink()
                    cleaned.append(task_id)
                except OSError:
                    pass

        return cleaned

    def list_locks(self) -> list[LockInfo]:
        """列出所有当前有效的锁。

        Returns:
            有效锁的列表
        """
        locks: list[LockInfo] = []

        if not self.locks_dir.exists():
            return locks

        for lock_file in self.locks_dir.glob("*.lock"):
            try:
                lock_info = LockInfo.from_json(lock_file.read_text(encoding="utf-8"))
                if not lock_info.is_expired():
                    locks.append(lock_info)
            except (json.JSONDecodeError, KeyError):
                pass

        return locks

    def force_release_all(self) -> int:
        """强制释放所有锁。

        Returns:
            释放的锁数量
        """
        count = 0

        if not self.locks_dir.exists():
            return count

        for lock_file in self.locks_dir.glob("*.lock"):
            try:
                lock_file.unlink()
                count += 1
            except OSError:
                pass

        return count
