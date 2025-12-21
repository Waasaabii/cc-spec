"""Unit tests for config module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from cc_spec.core.config import (
    AgentsConfig,
    ChecklistConfig,
    Config,
    SubAgentConfig,
    SubAgentProfile,
    detect_agent,
    load_config,
    read_tech_requirements,
    save_config,
)


class TestAgentsConfig:
    """Tests for AgentsConfig dataclass."""

    def test_default_values(self) -> None:
        """Test AgentsConfig default values."""
        config = AgentsConfig()
        assert config.enabled == ["claude"]
        assert config.default == "claude"

    def test_custom_values(self) -> None:
        """Test AgentsConfig with custom values."""
        config = AgentsConfig(
            enabled=["claude", "cursor", "gemini"],
            default="cursor",
        )
        assert len(config.enabled) == 3
        assert config.default == "cursor"

    def test_to_dict(self) -> None:
        """Test AgentsConfig.to_dict() method."""
        config = AgentsConfig(enabled=["claude", "gemini"], default="gemini")
        data = config.to_dict()
        assert data["enabled"] == ["claude", "gemini"]
        assert data["default"] == "gemini"

    def test_from_dict(self) -> None:
        """Test AgentsConfig.from_dict() method."""
        data = {"enabled": ["cursor", "qwen"], "default": "qwen"}
        config = AgentsConfig.from_dict(data)
        assert config.enabled == ["cursor", "qwen"]
        assert config.default == "qwen"

    def test_from_dict_partial(self) -> None:
        """Test AgentsConfig.from_dict() with partial data."""
        data = {"enabled": ["amazonq"]}
        config = AgentsConfig.from_dict(data)
        assert config.enabled == ["amazonq"]
        assert config.default == "claude"  # Default value


class TestSubAgentProfile:
    """Tests for SubAgentProfile dataclass."""

    def test_default_values(self) -> None:
        """Test SubAgentProfile default values."""
        profile = SubAgentProfile()
        assert profile.model == "sonnet"
        assert profile.timeout == 300000
        assert profile.permissionMode == "default"
        assert profile.tools is None
        assert profile.description == ""

    def test_custom_values(self) -> None:
        """Test SubAgentProfile with custom values."""
        profile = SubAgentProfile(
            model="opus",
            timeout=600000,
            permissionMode="acceptEdits",
            tools="Read,Write,Glob",
            description="Heavy tasks",
        )
        assert profile.model == "opus"
        assert profile.timeout == 600000
        assert profile.permissionMode == "acceptEdits"
        assert profile.tools == "Read,Write,Glob"
        assert profile.description == "Heavy tasks"

    def test_to_dict(self) -> None:
        """Test SubAgentProfile.to_dict() method."""
        profile = SubAgentProfile(model="haiku", description="Quick tasks")
        data = profile.to_dict()
        assert data["model"] == "haiku"
        assert data["timeout"] == 300000
        assert "tools" not in data  # None values omitted
        assert data["description"] == "Quick tasks"

    def test_from_dict(self) -> None:
        """Test SubAgentProfile.from_dict() method."""
        data = {"model": "opus", "timeout": 600000, "tools": "Read,Glob"}
        profile = SubAgentProfile.from_dict(data)
        assert profile.model == "opus"
        assert profile.timeout == 600000
        assert profile.tools == "Read,Glob"


class TestSubAgentConfig:
    """Tests for SubAgentConfig dataclass."""

    def test_default_values(self) -> None:
        """Test SubAgentConfig default values."""
        config = SubAgentConfig()
        assert config.max_concurrent == 10
        assert config.timeout == 300000

    def test_custom_values(self) -> None:
        """Test SubAgentConfig with custom values."""
        config = SubAgentConfig(max_concurrent=5, timeout=60000)
        assert config.max_concurrent == 5
        assert config.timeout == 60000

    def test_get_profile_default(self) -> None:
        """Test SubAgentConfig.get_profile() returns common for default."""
        common = SubAgentProfile(model="sonnet", timeout=300000)
        config = SubAgentConfig(common=common)

        profile = config.get_profile(None)
        assert profile.model == "sonnet"

        profile = config.get_profile("default")
        assert profile.model == "sonnet"

    def test_get_profile_named(self) -> None:
        """Test SubAgentConfig.get_profile() returns named profile."""
        common = SubAgentProfile(model="sonnet", timeout=300000)
        profiles = {
            "quick": SubAgentProfile(model="haiku", timeout=60000),
            "heavy": SubAgentProfile(model="opus", timeout=600000),
        }
        config = SubAgentConfig(common=common, profiles=profiles)

        quick = config.get_profile("quick")
        assert quick.model == "haiku"
        assert quick.timeout == 60000

        heavy = config.get_profile("heavy")
        assert heavy.model == "opus"

    def test_get_profile_unknown(self) -> None:
        """Test SubAgentConfig.get_profile() returns common for unknown profile."""
        common = SubAgentProfile(model="sonnet")
        config = SubAgentConfig(common=common)

        profile = config.get_profile("nonexistent")
        assert profile.model == "sonnet"


class TestChecklistConfig:
    """Tests for ChecklistConfig dataclass."""

    def test_default_values(self) -> None:
        """Test ChecklistConfig default values."""
        config = ChecklistConfig()
        assert config.pass_threshold == 80
        assert config.auto_retry is False

    def test_custom_values(self) -> None:
        """Test ChecklistConfig with custom values."""
        config = ChecklistConfig(pass_threshold=90, auto_retry=True)
        assert config.pass_threshold == 90
        assert config.auto_retry is True


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_values(self) -> None:
        """Test Config default values."""
        config = Config()
        assert config.version == "1.4"  # default
        assert config.agent == "claude"
        assert config.project_name == "my-project"
        assert ".claude/CLAUDE.md" in config.tech_requirements_sources
        assert isinstance(config.subagent, SubAgentConfig)
        assert isinstance(config.checklist, ChecklistConfig)
        assert config.kb.chunking.strategy == "ast-only"

    def test_custom_values(self) -> None:
        """Test Config with custom values."""
        config = Config(
            version="2.0",
            agent="cursor",
            project_name="test-project",
            tech_requirements_sources=["custom.md"],
            subagent=SubAgentConfig(max_concurrent=3),
            checklist=ChecklistConfig(pass_threshold=70),
        )
        assert config.version == "2.0"
        assert config.agent == "cursor"
        assert config.project_name == "test-project"
        assert config.tech_requirements_sources == ["custom.md"]
        assert config.subagent.max_concurrent == 3
        assert config.checklist.pass_threshold == 70

    def test_to_dict(self) -> None:
        """Test Config.to_dict() method."""
        config = Config(
            version="1.2",
            agent="gemini",
            project_name="test",
            agents=AgentsConfig(enabled=["gemini"], default="gemini"),
        )
        data = config.to_dict()

        assert data["version"] == "1.2"
        # uses agents instead of agent
        assert data["agents"]["default"] == "gemini"
        assert data["agents"]["enabled"] == ["gemini"]
        assert data["project_name"] == "test"
        assert isinstance(data["tech_requirements_sources"], list)
        assert isinstance(data["subagent"], dict)
        assert data["subagent"]["max_concurrent"] == 10
        assert isinstance(data["checklist"], dict)
        assert data["checklist"]["pass_threshold"] == 80

    def test_from_dict(self) -> None:
        """Test Config.from_dict() method."""
        data = {
            "version": "1.5",
            "agent": "cursor",
            "project_name": "my-test",
            "tech_requirements_sources": ["test.md"],
            "subagent": {
                "max_concurrent": 5,
                "timeout": 60000,
            },
            "checklist": {
                "pass_threshold": 85,
                "auto_retry": True,
            },
        }
        config = Config.from_dict(data)

        assert config.version == "1.5"
        assert config.agent == "cursor"
        assert config.project_name == "my-test"
        assert config.tech_requirements_sources == ["test.md"]
        assert config.subagent.max_concurrent == 5
        assert config.subagent.timeout == 60000
        assert config.checklist.pass_threshold == 85
        assert config.checklist.auto_retry is True

    def test_from_dict_partial(self) -> None:
        """Test Config.from_dict() with partial data (should use defaults)."""
        data = {
            "agent": "claude",
        }
        config = Config.from_dict(data)

        assert config.version == "1.4"  # default
        assert config.agent == "claude"
        assert config.project_name == "my-project"
        assert config.subagent.max_concurrent == 10
        assert config.checklist.pass_threshold == 80

    def test_agents_config_v12(self) -> None:
        """Test Config with AgentsConfig."""
        config = Config(
            version="1.2",
            agent="claude",
            agents=AgentsConfig(
                enabled=["claude", "cursor", "gemini"],
                default="cursor",
            ),
        )
        assert config.agents.enabled == ["claude", "cursor", "gemini"]
        assert config.agents.default == "cursor"

    def test_get_active_agent_with_agents_config(self) -> None:
        """Test Config.get_active_agent() with AgentsConfig."""
        config = Config(
            agent="claude",
            agents=AgentsConfig(enabled=["cursor", "gemini"], default="gemini"),
        )
        # Should return agents.default when agents is configured
        assert config.get_active_agent() == "gemini"

    def test_get_active_agent_fallback(self) -> None:
        """Test Config.get_active_agent() falls back to agent field."""
        # Create config with empty agents.enabled to trigger fallback
        config = Config(
            agent="cursor",
            agents=AgentsConfig(enabled=[], default=""),  # Empty config
        )
        # When agents.enabled is empty, should fall back to agent field
        assert config.get_active_agent() == "cursor"

    def test_from_dict_with_agents(self) -> None:
        """Test Config.from_dict() with agents field."""
        data = {
            "version": "1.2",
            "agent": "claude",
            "agents": {
                "enabled": ["claude", "amazonq"],
                "default": "amazonq",
            },
            "project_name": "test",
        }
        config = Config.from_dict(data)
        assert config.agents.enabled == ["claude", "amazonq"]
        assert config.agents.default == "amazonq"
        assert config.get_active_agent() == "amazonq"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_success(self) -> None:
        """Test loading config from valid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"

            # Write test config
            config_data = {
                "version": "1.0",
                "agent": "cursor",
                "project_name": "test-project",
                "tech_requirements_sources": ["test.md"],
                "subagent": {
                    "max_concurrent": 5,
                    "timeout": 60000,
                },
                "checklist": {
                    "pass_threshold": 90,
                    "auto_retry": True,
                },
            }
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config_data, f)

            # Load config
            config = load_config(config_path)

            assert config.version == "1.0"
            assert config.agent == "cursor"
            assert config.project_name == "test-project"
            assert config.tech_requirements_sources == ["test.md"]
            assert config.subagent.max_concurrent == 5
            assert config.checklist.pass_threshold == 90

    def test_load_config_empty_file(self) -> None:
        """Test loading config from empty YAML file (should use defaults)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("", encoding="utf-8")

            config = load_config(config_path)

            assert config.version == "1.4"  # default
            assert config.agent == "claude"
            assert config.project_name == "my-project"

    def test_load_config_file_not_found(self) -> None:
        """Test loading config from non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.yaml"

            with pytest.raises(FileNotFoundError):
                load_config(config_path)

    def test_load_config_invalid_yaml(self) -> None:
        """Test loading config from malformed YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("invalid: yaml: content: [", encoding="utf-8")

            with pytest.raises(yaml.YAMLError):
                load_config(config_path)


class TestSaveConfig:
    """Tests for save_config function."""

    def test_save_config_success(self) -> None:
        """Test saving config to YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"

            config = Config(
                version="1.2",
                agent="gemini",
                project_name="save-test",
                agents=AgentsConfig(enabled=["gemini"], default="gemini"),
            )

            save_config(config, config_path)

            assert config_path.exists()

            # Load and verify
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # uses agents field instead of agent
            assert data["agents"]["default"] == "gemini"
            assert data["project_name"] == "save-test"
            assert data["version"] == "1.2"

    def test_save_config_creates_directory(self) -> None:
        """Test save_config creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "subdir" / "config.yaml"

            config = Config()
            save_config(config, config_path)

            assert config_path.exists()
            assert config_path.parent.exists()


class TestDetectAgent:
    """Tests for detect_agent function."""

    def test_detect_claude(self) -> None:
        """Test detecting Claude Code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".claude").mkdir()

            agent = detect_agent(project_root)
            assert agent == "claude"

    def test_detect_cursor(self) -> None:
        """Test detecting Cursor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".cursor").mkdir()

            agent = detect_agent(project_root)
            assert agent == "cursor"

    def test_detect_gemini(self) -> None:
        """Test detecting Gemini CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".gemini").mkdir()

            agent = detect_agent(project_root)
            assert agent == "gemini"

    def test_detect_unknown(self) -> None:
        """Test detecting unknown agent (no markers present)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            agent = detect_agent(project_root)
            assert agent == "unknown"

    def test_detect_multiple_agents(self) -> None:
        """Test detecting when multiple agents are present (first match wins)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / ".claude").mkdir()
            (project_root / ".cursor").mkdir()

            agent = detect_agent(project_root)
            # Should return the first match in the agent_markers dict
            assert agent in ["claude", "cursor"]


class TestReadTechRequirements:
    """Tests for read_tech_requirements function."""

    def test_read_existing_files(self) -> None:
        """Test reading technical requirements from existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create test files
            claude_md = project_root / ".claude" / "CLAUDE.md"
            claude_md.parent.mkdir(parents=True)
            claude_md.write_text("# Claude Config\nTest content", encoding="utf-8")

            agents_md = project_root / "AGENTS.md"
            agents_md.write_text("# Agents\nMore content", encoding="utf-8")

            sources = [".claude/CLAUDE.md", "AGENTS.md", "nonexistent.md"]
            requirements = read_tech_requirements(project_root, sources)

            assert ".claude/CLAUDE.md" in requirements
            assert "# Claude Config" in requirements[".claude/CLAUDE.md"]
            assert "AGENTS.md" in requirements
            assert "# Agents" in requirements["AGENTS.md"]
            assert "nonexistent.md" in requirements
            assert requirements["nonexistent.md"] == ""

    def test_read_empty_sources(self) -> None:
        """Test reading with empty sources list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            requirements = read_tech_requirements(project_root, [])
            assert requirements == {}

    def test_read_nonexistent_files(self) -> None:
        """Test reading when all files don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            sources = ["missing1.md", "missing2.md"]
            requirements = read_tech_requirements(project_root, sources)

            assert len(requirements) == 2
            assert requirements["missing1.md"] == ""
            assert requirements["missing2.md"] == ""
