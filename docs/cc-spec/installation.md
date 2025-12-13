# 安装指南

## 系统要求

- **Python**: 3.12 或更高版本
- **操作系统**: Windows, macOS, Linux

## 安装方法

### 方法 1: 使用 uv (推荐)

[uv](https://github.com/astral-sh/uv) 是一个快速的 Python 包管理器，推荐使用。

```bash
# 安装 uv (如果尚未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 cc-spec
uv pip install cc-spec
```

### 方法 2: 使用 pip

```bash
pip install cc-spec
```

### 方法 3: 从源码安装

```bash
# 克隆仓库
git clone https://github.com/Waasaabii/cc-spec.git
cd cc-spec

# 使用 uv 安装开发版本
uv pip install -e .

# 或使用 pip
pip install -e .
```

## 验证安装

安装完成后，运行以下命令验证：

```bash
cc-spec --version
# 输出: cc-spec version 0.1.0

cc-spec --help
# 显示所有可用命令
```

## 依赖项

cc-spec 依赖以下核心库：

| 依赖 | 用途 |
|------|------|
| typer | CLI 框架 |
| rich | 终端 UI 和格式化 |
| pyyaml | YAML 配置解析 |
| httpx | HTTP 请求 (模板下载) |

这些依赖会在安装时自动安装。

## 配置

### 全局配置

cc-spec 支持全局配置，存储在用户目录：

```
~/.cc-spec/
├── config.yaml      # 全局配置
└── templates/       # 全局模板
```

### 项目配置

项目级配置存储在项目根目录：

```
.cc-spec/
├── config.yaml      # 项目配置 (覆盖全局)
└── templates/       # 项目模板 (覆盖全局)
```

### 配置文件格式

```yaml
# config.yaml
version: "1.0"
agent:
  type: "claude-code"  # AI 工具类型
  model: "claude-3"
templates:
  source: "github"     # 模板来源
  url: "https://github.com/Waasaabii/templates"
project:
  name: "my-project"
  language: "python"
```

## 升级

### 使用 uv

```bash
uv pip install --upgrade cc-spec
```

### 使用 pip

```bash
pip install --upgrade cc-spec
```

## 卸载

```bash
# 使用 uv
uv pip uninstall cc-spec

# 或使用 pip
pip uninstall cc-spec
```

## 常见问题

### Q: 安装时出现权限错误

使用虚拟环境可以避免权限问题：

```bash
# 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# 安装
uv pip install cc-spec
```

### Q: 找不到 cc-spec 命令

确保 Python 的 Scripts 目录在 PATH 中：

```bash
# Linux/macOS
export PATH="$HOME/.local/bin:$PATH"

# Windows (PowerShell)
$env:Path += ";$env:USERPROFILE\.local\bin"
```

### Q: 如何使用代理下载模板

设置环境变量：

```bash
# Linux/macOS
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=http://proxy:port

# Windows
set HTTP_PROXY=http://proxy:port
set HTTPS_PROXY=http://proxy:port
```
