"""清理项目临时构建文件

用法:
    python scripts/cleanup.py

将删除常见的构建产物、缓存与临时文件（不会删除源码）。
说明：当前仅保留 PyInstaller 打包流程（已移除 Nuitka 打包）。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _remove_path(p: Path) -> None:
    if not p.exists():
        return
    try:
        if p.is_dir():
            print("删除目录：", p)
            shutil.rmtree(p)
        else:
            print("删除文件：", p)
            p.unlink()
    except Exception as e:
        print("删除失败：", p, e)


dirs_to_remove = [
    ROOT / "build",
    ROOT / "dist",
    ROOT / "bin",  # C 构建输出
    ROOT / "__pycache__",
    ROOT / "logs",
    ROOT / "installer" / "build",
    ROOT / "installer" / "dist",
    ROOT / "installer" / "__pycache__",
    ROOT / "src" / "python" / "__pycache__",
]

files_to_remove = [
    ROOT / "installer" / "version.tmp",
    ROOT / "installer" / "Remote-Controls-temp.iss",
]

for p in dirs_to_remove:
    _remove_path(p)

for p in files_to_remove:
    _remove_path(p)

print("清理完成")
