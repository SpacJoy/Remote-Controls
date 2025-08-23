"""清理项目临时构建文件

用法:
    python scripts/cleanup.py

将删除常见的构建产物、缓存与临时文件（不会删除源码）。
"""
import shutil
import os

ROOT = os.path.dirname(os.path.dirname(__file__))

paths = [
    # os.path.join(ROOT, '.venv'),
    os.path.join(ROOT, 'build'),
    os.path.join(ROOT, 'dist'),
    os.path.join(ROOT, '__pycache__'),
    os.path.join(ROOT, 'installer', 'build'),
    os.path.join(ROOT, 'installer', 'dist'),
    os.path.join(ROOT, 'installer', 'build-nuitka'),
    os.path.join(ROOT, 'installer', 'dist-nuitka'),
]

for p in paths:
    if os.path.exists(p):
        try:
            print('Removing', p)
            shutil.rmtree(p)
        except Exception as e:
            print('Failed to remove', p, e)

print('Cleanup finished')
