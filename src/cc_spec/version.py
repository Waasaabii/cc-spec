"""cc-spec 版本常量（集中管理）。

注意：这里同时包含多个“版本维度”，它们的含义不同：
- PACKAGE_VERSION：cc-spec CLI/库自身版本
- TASKS_YAML_VERSION：tasks.yaml 的 schema 版本
- CONFIG_VERSION：.cc-spec/config.yaml 的 schema 版本
- KB_SCHEMA_VERSION：KB manifest/events 相关的 schema 版本
"""

__version__ = "0.1.6"
PACKAGE_VERSION = __version__
TASKS_YAML_VERSION = "1.6"
CONFIG_VERSION = "1.3"
KB_SCHEMA_VERSION = "0.1.6"

EMBEDDING_SERVER_VERSION = f"cc-spec-embedding/{PACKAGE_VERSION}"
UI_VERSION_INFO = f"v{PACKAGE_VERSION} - Smart Context Injection"
