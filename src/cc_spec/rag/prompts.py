"""v0.1.5: Prompt templates for Codex chunking/summarization."""

from __future__ import annotations


def chunk_file_prompt(*, rel_path: str, content: str) -> str:
    """Ask Codex to chunk a file into semantic chunks and return a strict JSON array."""
    return f"""You are a *file chunker*. **Do not modify any files. Do not run any commands.**

Goal: chunk the given file into meaningful semantic chunks and return **STRICT JSON**.
Output MUST be JSON only (no explanations, no markdown).

Input file: `{rel_path}`

Output requirements:
- Output MUST be a JSON array (list)
- Each element MUST be an object with fields:
  - id: string (short, stable, readable)
  - type: string (one of: function/class/module/section/config/other)
  - summary: string (English preferred, <= 120 chars)
  - content: string (verbatim snippet for this chunk; keep necessary context)
  - start_line: number|null (optional)
  - end_line: number|null (optional)

Forbidden:
- No Markdown
- No ``` fences
- No extra fields

File content (verbatim):\n\n{content}
"""


def chunk_files_prompt(*, files: list[dict[str, str]]) -> str:
    """Ask Codex to chunk multiple files in one call.

    Output is a strict JSON array of:
      {"path": "<rel_path>", "chunks": [ ...chunk objects... ]}

    Each chunk object must follow the same schema as `chunk_file_prompt`.
    """
    blocks: list[str] = []
    for f in files:
        path = f.get("path", "")
        mode = f.get("mode", "chunk")
        content = f.get("content", "")
        blocks.append(f'FILE_BEGIN path="{path}" mode="{mode}"\n{content}\nFILE_END')

    joined = "\n\n".join(blocks)
    return f"""You are a *batch file chunker*. **Do not modify any files. Do not run any commands.**

Goal: chunk each provided file into meaningful semantic chunks and return **STRICT JSON**.
Output MUST be JSON only (no explanations, no markdown).

Output requirements:
- Output MUST be a JSON array (list)
- Each element MUST be an object with fields:
  - path: string (must match input path exactly)
  - chunks: JSON array (list) of chunk objects
- Each chunk object MUST have fields:
  - id: string (short, stable, readable)
  - type: string (one of: function/class/module/section/config/other OR "reference_index")
  - summary: string (English preferred, <= 120 chars; <= 200 for reference_index)
  - content: string (verbatim snippet for this chunk; keep necessary context)
  - start_line: number|null (optional)
  - end_line: number|null (optional)

Mode rules:
- mode="reference_index": return exactly 1 chunk with type="reference_index", id="file_index",
  summary<=200 chars, and content containing key facts/TOC/entry points (do NOT restate full text).
- mode="chunk": chunk normally.

Forbidden:
- No Markdown
- No ``` fences
- No extra top-level fields
- No extra chunk fields

Input files:\n\n{joined}
"""


def reference_index_prompt(*, rel_path: str, content: str) -> str:
    """Index-level summary for reference/**: small tokens but searchable."""
    excerpt = content[:8000]
    return f"""You are a *reference indexer*. **Do not modify any files. Do not run any commands.**

Goal: create an *index-level* summary for a file under `reference/` so it is searchable,
and can be deep-chunked later if needed.

Input file: `{rel_path}`

Output requirements:
- Output MUST be a strict JSON array (list)
- Each element MUST be an object with fields:
  - id: string (use something like "file_index")
  - type: string (always "reference_index")
  - summary: string (English preferred, <= 200 chars)
  - content: string (key facts, table of contents, entry points; do NOT restate the full text)

File excerpt (may be truncated):\n\n{excerpt}
"""
