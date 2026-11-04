# -*- coding: utf-8 -*-
"""路径与配置：所有数据都落在项目目录内

目录约定（源码运行 / 打包运行一致）：

    <项目根>/
      frontend/     页面（只读）
      backend/      服务端代码（只读）
      resources/    内置游戏资源包（只读）
      skland/       ★ 用户数据：tokens.txt、accounts/*.json、subprof_cache.json
      config/       ★ 用户数据：settings.json、app.log

「项目根」判定：
  - 源码运行：settings.py 往上三层
  - 打包运行：从 exe 目录逐级向上找，第一个同时含 frontend/ 与 backend/ 的目录；
              找不到（例如把 dist/MAA-PRTS 单独拷走）就用 exe 所在目录
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading

FROZEN = bool(getattr(sys, 'frozen', False))


def _looks_like_project(path: str) -> bool:
    return (os.path.isdir(os.path.join(path, 'frontend'))
            and os.path.isdir(os.path.join(path, 'backend')))


def _source_root() -> str:
    # <root>/backend/core/settings.py → <root>
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def project_root() -> str:
    """可写的项目根目录（数据落在它下面）"""
    if not FROZEN:
        return _source_root()
    d = os.path.dirname(os.path.abspath(sys.executable))
    cur = d
    for _ in range(4):
        if _looks_like_project(cur):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return d


def resource_root() -> str:
    """只读资源目录：打包后是 PyInstaller 的临时解包目录"""
    if FROZEN:
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    return _source_root()


ROOT = project_root()
RES = resource_root()

STATIC_DIR = os.path.join(RES, 'frontend')
PACK_PATH = os.path.join(RES, 'resources', 'arknights.json')

SKLAND_DIR = os.path.join(ROOT, 'skland')
ACCOUNTS_DIR = os.path.join(SKLAND_DIR, 'accounts')
CONFIG_DIR = os.path.join(ROOT, 'config')
SETTINGS_PATH = os.path.join(CONFIG_DIR, 'settings.json')
LOG_PATH = os.path.join(CONFIG_DIR, 'app.log')

for _d in (SKLAND_DIR, ACCOUNTS_DIR, CONFIG_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except Exception:
        pass

DEFAULTS = {
    'maaDir': '',
    'profile': 'moren',
    'autoStartMaa': True,
    'lastAccount': '',
}

_lock = threading.RLock()
_cache = None


def load() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
        data = dict(DEFAULTS)
        try:
            with io.open(SETTINGS_PATH, encoding='utf-8') as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except Exception:
            pass
        if os.environ.get('MAA_DIR'):
            data['maaDir'] = os.environ['MAA_DIR']
        _cache = data
        return dict(data)


def save(patch: dict) -> dict:
    global _cache
    with _lock:
        cur = load()
        for k, v in (patch or {}).items():
            if k not in DEFAULTS:
                continue
            if k == 'maaDir':
                # 容忍从资源管理器粘来的路径：正反斜杠混用、末尾带斜杠、双斜杠
                v = (v or '').strip().strip('"')
                if v:
                    v = os.path.normpath(v.replace('/', '\\'))
                    if v.endswith('\\') and len(v) > 3:
                        v = v.rstrip('\\')
            cur[k] = v
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = SETTINGS_PATH + '.tmp'
        with io.open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, SETTINGS_PATH)
        _cache = cur
        return dict(cur)


# ---------------------------------------------------------------- 派生路径
def skland_dir() -> str:
    return SKLAND_DIR


def accounts_dir() -> str:
    return ACCOUNTS_DIR


def tokens_file() -> str:
    return os.path.join(SKLAND_DIR, 'tokens.txt')


def subprof_cache() -> str:
    return os.path.join(SKLAND_DIR, 'subprof_cache.json')


def static_dir() -> str:
    return STATIC_DIR


def pack_path() -> str:
    """资源包路径

    优先用项目目录下的 resources/arknights.json：想换新资源包时，
    直接把它覆盖进来即可，不用重新打包；没有再回退到程序内置的那份。
    """
    local = os.path.join(ROOT, 'resources', 'arknights.json')
    if os.path.isfile(local):
        return local
    return PACK_PATH
