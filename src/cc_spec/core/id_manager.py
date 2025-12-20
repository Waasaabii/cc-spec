"""cc-spec  ID 管理模块。

该模块提供变更、任务、规格与归档的 ID 生成、解析与路径解析能力。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class IDType(Enum):
    """cc-spec 中 ID 的类型。"""

    CHANGE = "C"
    TASK = "T"
    SPEC = "S"
    ARCHIVE = "A"


@dataclass
class ParsedID:
    """解析后的 ID 信息。

    属性：
        type：ID 类型（CHANGE/TASK/SPEC/ARCHIVE）
        change_id：变更 ID（例如 "C-001"），如适用
        task_id：变更内的任务 ID（例如 "01-SETUP"），如适用
        full_id：原始完整 ID 字符串
    """

    type: IDType
    change_id: str | None
    task_id: str | None
    full_id: str


@dataclass
class ChangeEntry:
    """ID 映射中的变更条目。

    属性：
        name：变更的可读名称
        path：变更目录的相对路径
        created：ISO 格式的创建时间戳
    """

    name: str
    path: str
    created: str


@dataclass
class SpecEntry:
    """ID 映射中的规格条目。"""

    path: str


@dataclass
class ArchiveEntry:
    """ID 映射中的归档变更条目。"""

    name: str
    path: str


@dataclass
class IDMap:
    """ID 映射数据结构。

    属性：
        version：ID map 格式版本
        changes：change_id -> ChangeEntry 的映射
        specs：spec_id -> SpecEntry 的映射
        archive：archive_id -> ArchiveEntry 的映射
        next_change_id：下一个 change ID 的序号
    """

    version: str = "1.0"
    changes: dict[str, ChangeEntry] = field(default_factory=dict)
    specs: dict[str, SpecEntry] = field(default_factory=dict)
    archive: dict[str, ArchiveEntry] = field(default_factory=dict)
    next_change_id: int = 1

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以便 YAML 序列化。"""
        changes_dict = {}
        for cid, entry in self.changes.items():
            changes_dict[cid] = {
                "name": entry.name,
                "path": entry.path,
                "created": entry.created,
            }

        specs_dict = {}
        for sid, entry in self.specs.items():
            specs_dict[sid] = {"path": entry.path}

        archive_dict = {}
        for aid, entry in self.archive.items():
            archive_dict[aid] = {
                "name": entry.name,
                "path": entry.path,
            }

        return {
            "version": self.version,
            "changes": changes_dict,
            "specs": specs_dict,
            "archive": archive_dict,
            "next_change_id": self.next_change_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IDMap":
        """从字典创建 IDMap。"""
        changes = {}
        for cid, entry_data in data.get("changes", {}).items():
            changes[cid] = ChangeEntry(
                name=entry_data.get("name", ""),
                path=entry_data.get("path", ""),
                created=entry_data.get("created", ""),
            )

        specs = {}
        for sid, entry_data in data.get("specs", {}).items():
            specs[sid] = SpecEntry(path=entry_data.get("path", ""))

        archive = {}
        for aid, entry_data in data.get("archive", {}).items():
            archive[aid] = ArchiveEntry(
                name=entry_data.get("name", ""),
                path=entry_data.get("path", ""),
            )

        return cls(
            version=data.get("version", "1.0"),
            changes=changes,
            specs=specs,
            archive=archive,
            next_change_id=data.get("next_change_id", 1),
        )


class IDManager:
    """cc-spec 的 ID 管理器。

    负责所有 cc-spec 实体的 ID 生成、解析与路径解析。
    """

    def __init__(self, cc_spec_root: Path):
        """初始化 ID 管理器。

        参数：
            cc_spec_root：.cc-spec 目录路径
        """
        self.cc_spec_root = cc_spec_root
        self.id_map_path = cc_spec_root / "id-map.yaml"
        self._id_map: IDMap = self._load_id_map()

    def _load_id_map(self) -> IDMap:
        """从文件加载 ID map；若不存在则创建新的。

        返回：
            IDMap 实例
        """
        if not self.id_map_path.exists():
            # 创建新 ID map 并扫描已有变更
            id_map = IDMap()
            self._scan_existing_changes(id_map)
            self._save_id_map(id_map)
            return id_map

        try:
            with open(self.id_map_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                data = {}

            return IDMap.from_dict(data)
        except (yaml.YAMLError, OSError):
            # 如果文件损坏，则从零重建
            id_map = IDMap()
            self._scan_existing_changes(id_map)
            self._save_id_map(id_map)
            return id_map

    def _save_id_map(self, id_map: IDMap | None = None) -> None:
        """将 ID map 保存到文件。

        参数：
            id_map：要保存的 IDMap（不传则使用 self._id_map）
        """
        if id_map is None:
            id_map = self._id_map

        self.id_map_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.id_map_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                id_map.to_dict(),
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    def _scan_existing_changes(self, id_map: IDMap) -> None:
        """扫描已有 changes 目录并将其注册到 ID map。

        参数：
            id_map：需要填充的 IDMap
        """
        changes_dir = self.cc_spec_root / "changes"
        if not changes_dir.exists():
            return

        for change_dir in sorted(changes_dir.iterdir()):
            if not change_dir.is_dir():
                continue

            # 跳过 archive 目录
            if change_dir.name == "archive":
                continue

            # 检查是否为有效的变更目录
            status_file = change_dir / "status.yaml"
            if status_file.exists():
                # 注册该变更：直接操作 id_map
                # 避免访问尚未初始化的 self._id_map
                change_name = change_dir.name
                change_id = f"C-{id_map.next_change_id:03d}"
                id_map.next_change_id += 1
                id_map.changes[change_id] = ChangeEntry(
                    name=change_name,
                    path=f"changes/{change_name}",
                    created=datetime.now().isoformat(),
                )

    def generate_change_id(self) -> str:
        """生成新的唯一 change ID。

        返回：
            形如 "C-XXX" 的新 change ID
        """
        change_id = f"C-{self._id_map.next_change_id:03d}"
        self._id_map.next_change_id += 1
        return change_id

    def parse_id(self, id_str: str) -> ParsedID:
        """将 ID 字符串解析为结构化信息。

        支持的格式：
        - C-XXX：变更 ID
        - C-XXX:task-id：变更内的任务 ID
        - S-name：规格 ID
        - A-YYYYMMDD-XXX：归档 ID
        - name：按变更名称解析

        参数：
            id_str：待解析的 ID 字符串

        返回：
            带类型与各组件的 ParsedID

        异常：
            ValueError：当 ID 格式不合法时抛出
        """
        if ":" in id_str:
            # 任务 ID 格式：C-001:02-MODEL
            parts = id_str.split(":", 1)
            change_id = parts[0]
            task_id = parts[1]

            if not change_id.startswith("C-"):
                raise ValueError(f"任务 ID 格式不合法：{id_str}")

            return ParsedID(
                type=IDType.TASK,
                change_id=change_id,
                task_id=task_id,
                full_id=id_str,
            )

        if id_str.startswith("C-"):
            return ParsedID(
                type=IDType.CHANGE,
                change_id=id_str,
                task_id=None,
                full_id=id_str,
            )

        if id_str.startswith("S-"):
            return ParsedID(
                type=IDType.SPEC,
                change_id=None,
                task_id=None,
                full_id=id_str,
            )

        if id_str.startswith("A-"):
            return ParsedID(
                type=IDType.ARCHIVE,
                change_id=None,
                task_id=None,
                full_id=id_str,
            )

        # 尝试按变更名称解析
        resolved = self._resolve_by_name(id_str)
        if resolved:
            return resolved

        # 当作可能的新变更名称
        return ParsedID(
            type=IDType.CHANGE,
            change_id=None,
            task_id=None,
            full_id=id_str,
        )

    def _resolve_by_name(self, name: str) -> ParsedID | None:
        """尝试将名称解析为已有变更。

        参数：
            name：要查找的变更名称

        返回：
            找到则返回 ParsedID，否则返回 None
        """
        for change_id, entry in self._id_map.changes.items():
            if entry.name == name:
                return ParsedID(
                    type=IDType.CHANGE,
                    change_id=change_id,
                    task_id=None,
                    full_id=change_id,
                )
        return None

    def resolve_path(self, id_str: str) -> Path | None:
        """将 ID 解析为对应的文件系统路径。

        参数：
            id_str：要解析的 ID 字符串

        返回：
            对应实体的路径；未找到则返回 None
        """
        parsed = self.parse_id(id_str)

        if parsed.type == IDType.CHANGE and parsed.change_id:
            entry = self._id_map.changes.get(parsed.change_id)
            if entry:
                return self.cc_spec_root / entry.path
            return None

        if parsed.type == IDType.TASK and parsed.change_id:
            entry = self._id_map.changes.get(parsed.change_id)
            if entry:
                # 任务路径位于变更目录内
                return self.cc_spec_root / entry.path
            return None

        if parsed.type == IDType.SPEC:
            entry = self._id_map.specs.get(parsed.full_id)
            if entry:
                return self.cc_spec_root / entry.path
            return None

        if parsed.type == IDType.ARCHIVE:
            entry = self._id_map.archive.get(parsed.full_id)
            if entry:
                return self.cc_spec_root / entry.path
            return None

        return None

    def register_change(self, name: str, path: Path) -> str:
        """注册新变更并返回其 ID。

        参数：
            name：变更的可读名称
            path：变更目录路径（相对 cc_spec_root）

        返回：
            生成的变更 ID
        """
        change_id = self.generate_change_id()

        # 如有需要，将绝对路径转换为相对路径
        if path.is_absolute():
            try:
                rel_path = path.relative_to(self.cc_spec_root)
            except ValueError:
                rel_path = path
        else:
            rel_path = path

        self._id_map.changes[change_id] = ChangeEntry(
            name=name,
            path=str(rel_path).replace("\\", "/"),
            created=datetime.now().isoformat(),
        )

        self._save_id_map()
        return change_id

    def register_spec(self, name: str, path: Path) -> str:
        """注册规格并返回其 ID。

        参数：
            name：规格名称（用于生成 ID）
            path：规格目录路径

        返回：
            形如 "S-name" 的 spec ID
        """
        spec_id = f"S-{name}"

        if path.is_absolute():
            try:
                rel_path = path.relative_to(self.cc_spec_root)
            except ValueError:
                rel_path = path
        else:
            rel_path = path

        self._id_map.specs[spec_id] = SpecEntry(
            path=str(rel_path).replace("\\", "/")
        )

        self._save_id_map()
        return spec_id

    def register_archive(self, name: str, path: Path) -> str:
        """注册归档变更并返回其 ID。

        参数：
            name：变更原始名称
            path：归档变更路径

        返回：
            形如 "A-YYYYMMDD-XXX" 的归档 ID
        """
        today = datetime.now().strftime("%Y%m%d")

        # 统计今天已有的归档数量
        existing_today = sum(
            1 for aid in self._id_map.archive if aid.startswith(f"A-{today}")
        )

        archive_id = f"A-{today}-{existing_today + 1:03d}"

        if path.is_absolute():
            try:
                rel_path = path.relative_to(self.cc_spec_root)
            except ValueError:
                rel_path = path
        else:
            rel_path = path

        self._id_map.archive[archive_id] = ArchiveEntry(
            name=name,
            path=str(rel_path).replace("\\", "/"),
        )

        self._save_id_map()
        return archive_id

    def unregister_change(self, change_id: str) -> bool:
        """从 ID map 中移除一个变更。

        参数：
            change_id：要移除的变更 ID

        返回：
            成功移除则为 True；未找到则为 False
        """
        if change_id in self._id_map.changes:
            del self._id_map.changes[change_id]
            self._save_id_map()
            return True
        return False

    def get_change_entry(self, change_id: str) -> ChangeEntry | None:
        """通过 ID 获取变更条目。

        参数：
            change_id：要查找的变更 ID

        返回：
            找到则返回 ChangeEntry，否则返回 None
        """
        return self._id_map.changes.get(change_id)

    def get_change_by_name(self, name: str) -> tuple[str, ChangeEntry] | None:
        """通过名称获取变更条目。

        参数：
            name：要查找的变更名称

        返回：
            找到则返回 (change_id, entry)，否则返回 None
        """
        for change_id, entry in self._id_map.changes.items():
            if entry.name == name:
                return (change_id, entry)
        return None

    def list_changes(self) -> dict[str, ChangeEntry]:
        """列出所有已注册的变更。

        返回：
            change_id -> ChangeEntry 的字典
        """
        return dict(self._id_map.changes)

    def list_specs(self) -> dict[str, SpecEntry]:
        """列出所有已注册的规格。

        返回：
            spec_id -> SpecEntry 的字典
        """
        return dict(self._id_map.specs)

    def list_archive(self) -> dict[str, ArchiveEntry]:
        """列出所有已归档的变更。

        返回：
            archive_id -> ArchiveEntry 的字典
        """
        return dict(self._id_map.archive)

    def is_valid_id(self, id_str: str) -> bool:
        """检查一个 ID 字符串是否有效且存在。

        参数：
            id_str：要校验的 ID 字符串

        返回：
            有效且存在则为 True，否则为 False
        """
        try:
            parsed = self.parse_id(id_str)
        except ValueError:
            return False

        if parsed.type == IDType.CHANGE and parsed.change_id:
            return parsed.change_id in self._id_map.changes

        if parsed.type == IDType.TASK and parsed.change_id:
            return parsed.change_id in self._id_map.changes

        if parsed.type == IDType.SPEC:
            return parsed.full_id in self._id_map.specs

        if parsed.type == IDType.ARCHIVE:
            return parsed.full_id in self._id_map.archive

        return False

    def rebuild_from_directory(self) -> None:
        """通过扫描目录重建 ID map。

        当 id-map.yaml 损坏时可用于恢复。
        """
        self._id_map = IDMap()
        self._scan_existing_changes(self._id_map)

        # 同时扫描 specs 目录
        specs_dir = self.cc_spec_root / "specs"
        if specs_dir.exists():
            for spec_dir in specs_dir.iterdir():
                if spec_dir.is_dir():
                    spec_name = spec_dir.name
                    spec_id = f"S-{spec_name}"
                    self._id_map.specs[spec_id] = SpecEntry(
                        path=f"specs/{spec_name}"
                    )

        # 扫描 archive 目录
        archive_dir = self.cc_spec_root / "changes" / "archive"
        if archive_dir.exists():
            for archived_dir in sorted(archive_dir.iterdir()):
                if archived_dir.is_dir():
                    # 解析归档目录名（期望格式：YYYY-MM-DD-name）
                    dir_name = archived_dir.name
                    parts = dir_name.split("-", 3)
                    if len(parts) >= 4:
                        date_str = f"{parts[0]}{parts[1]}{parts[2]}"
                        name = parts[3]
                    else:
                        date_str = datetime.now().strftime("%Y%m%d")
                        name = dir_name

                    existing_today = sum(
                        1 for aid in self._id_map.archive
                        if aid.startswith(f"A-{date_str}")
                    )
                    archive_id = f"A-{date_str}-{existing_today + 1:03d}"

                    self._id_map.archive[archive_id] = ArchiveEntry(
                        name=name,
                        path=f"changes/archive/{dir_name}",
                    )

        self._save_id_map()
