#!/usr/bin/env python3
"""跑全部测试（零依赖，不需要 pytest）。"""

import importlib.util
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

tests = sorted(HERE.glob('test_*.py'))
passed = failed = 0

for t in tests:
    name = t.stem
    try:
        spec = importlib.util.spec_from_file_location(name, t)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # 跑该模块里所有 test_ 开头的函数
        for fn in dir(mod):
            if fn.startswith('test_') and callable(getattr(mod, fn)):
                getattr(mod, fn)()
        print(f'  ✅ {name}')
        passed += 1
    except Exception:
        print(f'  ❌ {name}')
        traceback.print_exc()
        failed += 1

print(f'\n通过 {passed} / 失败 {failed}')
sys.exit(0 if failed == 0 else 1)
