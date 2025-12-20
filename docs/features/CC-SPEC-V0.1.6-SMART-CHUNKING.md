# CC-SPEC v0.1.6: Smart Chunking Strategy

## 1. Problem Statement

当前 cc-spec 的 chunking 完全依赖 Codex：
- **Token 消耗**：每次切片都调用 Codex，token 成本高
- **速度慢**：Codex 调用平均 5-15 秒/文件，大项目 init 可能耗时数十分钟
- **Fallback 质量差**：Codex 失败时退化为简单行切分，不理解代码结构

## 2. Solution: Hybrid AST + LLM Chunking

### 2.1 策略分层

| 层级 | 文件类型 | 策略 | Token 消耗 | 质量 |
|------|----------|------|------------|------|
| **Tier 1** | 代码文件 (*.py, *.ts, etc.) | AST-based (tree-sitter) | 0 | 高 |
| **Tier 2** | 文档/配置 (*.md, *.yaml) | Line-based with overlap | 0 | 中 |
| **Tier 3** | 入口文件 (README, main.*) | LLM (Codex) | 高 | 极高 |

### 2.2 Why AST-based Works

基于 [astchunk](https://github.com/yilinjz/astchunk) 和 [code-splitter](https://github.com/wangxj03/code-splitter) 的调研：

**AST 切片的优势：**
1. **结构感知**：永远不会把函数/类切断
2. **语义边界**：按 AST 节点边界切分，保持代码完整性
3. **Metadata 丰富**：自动提取行号、祖先链（class/function path）
4. **速度飞快**：毫秒级，比 LLM 快 1000x
5. **零 Token**：纯本地计算

**语言支持：**
- 使用 [tree-sitter-language-pack](https://pypi.org/project/tree-sitter-language-pack/) 支持 100+ 语言
- 包括：Python, TypeScript, JavaScript, Go, Rust, Java, C#, C++, etc.

## 3. Architecture Design

### 3.1 新增 SmartChunker

```
src/cc_spec/rag/
├── chunker.py          # 现有 CodexChunker（保留，作为 LLM 策略）
├── ast_chunker.py      # 新增：AST-based chunker
└── smart_chunker.py    # 新增：策略调度器
```

### 3.2 SmartChunker 接口

```python
class SmartChunker:
    """智能切片调度器：根据文件类型选择最优策略。"""

    def __init__(
        self,
        codex: CodexClient,  # LLM fallback
        project_root: Path,
        options: SmartChunkingOptions | None = None,
    ):
        self.ast_chunker = ASTChunker()  # 零依赖
        self.codex_chunker = CodexChunker(codex, project_root)
        self.options = options or SmartChunkingOptions()

    def chunk_file(self, scanned: ScannedFile) -> ChunkResult:
        """根据文件类型选择策略。"""
        strategy = self._select_strategy(scanned)

        if strategy == ChunkStrategy.AST:
            return self.ast_chunker.chunk_file(scanned)
        elif strategy == ChunkStrategy.LINE:
            return self._line_chunk(scanned)
        elif strategy == ChunkStrategy.LLM:
            return self.codex_chunker.chunk_file(scanned)

    def _select_strategy(self, scanned: ScannedFile) -> ChunkStrategy:
        """策略选择逻辑。"""
        ext = scanned.rel_path.suffix.lower()
        name = scanned.rel_path.name.lower()

        # Tier 3: 入口文件用 LLM（生成高质量摘要）
        if name in self.options.llm_priority_files:
            return ChunkStrategy.LLM

        # Tier 1: 代码文件用 AST
        if ext in self.options.ast_supported_extensions:
            return ChunkStrategy.AST

        # Tier 2: 其他文件用行切分
        return ChunkStrategy.LINE
```

### 3.3 配置项

```python
@dataclass
class SmartChunkingOptions:
    # AST 策略参数
    max_chunk_chars: int = 2000  # 每个 chunk 最大非空白字符数
    chunk_overlap_nodes: int = 1  # 相邻 chunk 重叠的 AST 节点数

    # 策略选择
    ast_supported_extensions: set[str] = field(default_factory=lambda: {
        ".py", ".ts", ".tsx", ".js", ".jsx",  # 常用
        ".go", ".rs", ".java", ".kt", ".cs",  # 系统级
        ".c", ".cpp", ".h", ".hpp",           # C/C++
        ".rb", ".php", ".swift", ".scala",    # 其他
    })

    llm_priority_files: set[str] = field(default_factory=lambda: {
        "readme.md", "readme", "main.py", "app.py", "index.ts", "index.js",
        "__init__.py", "setup.py", "pyproject.toml", "package.json",
    })

    # Line 策略参数
    lines_per_chunk: int = 100
    overlap_lines: int = 10
```

## 4. ASTChunker Implementation

基于 astchunk 的核心算法，简化适配：

```python
class ASTChunker:
    """基于 tree-sitter 的 AST 切片器。"""

    def __init__(self, max_chunk_chars: int = 2000):
        self.max_chunk_chars = max_chunk_chars
        self._parsers: dict[str, Parser] = {}  # 缓存 parser

    def chunk_file(self, scanned: ScannedFile) -> ChunkResult:
        ext = scanned.rel_path.suffix.lower()
        lang = self._ext_to_lang(ext)

        if lang is None:
            # 不支持的语言，返回空让调度器 fallback
            return ChunkResult(chunks=[], status=ChunkStatus.UNSUPPORTED)

        parser = self._get_parser(lang)
        content = scanned.abs_path.read_text(encoding="utf-8")

        # 解析 AST
        tree = parser.parse(content.encode("utf-8"))

        # 贪婪分配到 windows
        windows = self._assign_to_windows(content, tree.root_node)

        # 转换为 Chunk 对象
        chunks = self._windows_to_chunks(
            windows,
            source_path=scanned.rel_path.as_posix(),
            source_sha256=scanned.sha256,
        )

        return ChunkResult(chunks=chunks, status=ChunkStatus.SUCCESS)
```

## 5. Benefits

### 5.1 Token 节省

| 场景 | 原方案 | 新方案 | 节省 |
|------|--------|--------|------|
| 100 个 Python 文件 | ~50K tokens | ~5K tokens (仅入口) | **90%** |
| 全栈项目 (500 文件) | ~250K tokens | ~25K tokens | **90%** |

### 5.2 速度提升

| 场景 | 原方案 | 新方案 | 提升 |
|------|--------|--------|------|
| 100 个文件 | ~10 分钟 | ~10 秒 | **60x** |
| 500 个文件 | ~50 分钟 | ~30 秒 | **100x** |

### 5.3 质量保证

- **代码文件**：AST 切片质量 ≈ LLM（不切断函数/类）
- **入口文件**：保留 LLM 生成高质量摘要
- **Metadata**：AST 自动提供行号、祖先链，无需 LLM

## 6. Implementation Plan

### Phase 1: AST Chunker Core
1. 添加 `tree-sitter-language-pack` 依赖
2. 实现 `ASTChunker` 类（基于 astchunk 算法）
3. 单元测试

### Phase 2: SmartChunker Integration
1. 实现 `SmartChunker` 调度器
2. 更新 `kb init`/`kb update` 使用 SmartChunker
3. 集成测试

### Phase 3: Configuration
1. 添加配置项到 `config.yaml`
2. 支持用户自定义策略优先级
3. 文档更新

## 7. Dependencies

```toml
# pyproject.toml
[project.dependencies]
tree-sitter-language-pack = ">=0.7.0"  # 100+ languages
```

## 8. References

- [astchunk](https://github.com/yilinjz/astchunk) - AST-based code chunking (Python)
- [code-splitter](https://github.com/wangxj03/code-splitter) - Rust-based splitter with Python bindings
- [tree-sitter-language-pack](https://pypi.org/project/tree-sitter-language-pack/) - 100+ language parsers
- [cAST Paper](https://arxiv.org/abs/2506.15655) - Research on AST chunking for code RAG

## 9. Summary

**核心思路**：
1. **代码文件用 AST**：0 token，快，质量好
2. **入口文件用 LLM**：少量 token 换高质量摘要
3. **其他文件用行切分**：0 token，够用

**ROI**：
- Token 成本降低 **90%**
- Init 速度提升 **60-100x**
- 切片质量不降反升（AST 结构感知）
