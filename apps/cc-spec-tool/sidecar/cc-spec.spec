# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for cc-spec sidecar.

Build command:
    pyinstaller --clean cc-spec.spec

Output: dist/cc-spec.exe (Windows) or dist/cc-spec (Unix)
"""

import sys
from pathlib import Path

# 项目根目录
# PyInstaller 在执行 spec 时不一定注入 `__file__`（PyInstaller 6.17+），推荐使用 SPECPATH。
spec_dir = Path(globals().get("SPECPATH", Path.cwd())).resolve()
project_root = spec_dir.parent.parent.parent
src_path = project_root / "src"

# 分析配置
a = Analysis(
    [str(src_path / "cc_spec" / "sidecar.py")],
    pathex=[str(src_path)],
    binaries=[],
    datas=[
        # 包含模板文件
        (str(src_path / "cc_spec" / "templates"), "cc_spec/templates"),
    ],
    hiddenimports=[
        "cc_spec",
        "cc_spec.commands",
        "cc_spec.core",
        "cc_spec.ui",
        "cc_spec.utils",
        "cc_spec.codex",
        "typer",
        "rich",
        "yaml",
        "httpx",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除重量级依赖
        "onnxruntime",
        "torch",
        "tensorflow",
        "transformers",
        "numpy",  # 如果不需要的话
        "pandas",
        "matplotlib",
        "PIL",
        "cv2",
        # 排除不需要的标准库
        "tkinter",
        "unittest",
        "test",
    ],
    noarchive=False,
)

# 过滤大型二进制文件
a.binaries = [
    (name, path, type_)
    for name, path, type_ in a.binaries
    if not any(
        exclude in name.lower()
        for exclude in ["torch", "cuda", "cudnn", "onnx", "tensorflow"]
    )
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="cc-spec",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # 使用 UPX 压缩
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # CLI 工具需要控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标
)
