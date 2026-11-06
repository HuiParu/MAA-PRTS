# -*- coding: utf-8 -*-
"""路径与配置：所有数据都落在运行根目录内

目录约定（源码运行 / 打包运行一致）：

    <运行根>/
      frontend/     页面（只读）
      backend/      服务端代码（只读）
      resources/    内置游戏资源包（只读）
      config/       ★ 用户数据：settings.json、gamedata.json、
                                 skland/（tokens.json 加密、accounts/、缓存）
      debug/        运行日志 app.log（随时可删）

「运行根」＝程序在哪个目录运行，数据就落在哪个目录，任何模式都不向上找：
  - 打包运行：exe 所在目录
  - 源码运行：启动时的工作目录（启动.bat / 打包.bat 都会先 cd 到仓库根）
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading

FROZEN = bool(getattr(sys, 'frozen', False))

# 运行根：可写数据（config/、debug/）落在这里
ROOT = (os.path.dirname(os.path.abspath(sys.executable)) if FROZEN
        else os.path.abspath(os.getcwd()))
# 只读资源根：打包后在 PyInstaller 的解包目录里，源码运行与运行根同处
RES = (getattr(sys, '_MEIPASS', ROOT) if FROZEN else ROOT)


def project_root() -> str:
    """可写的运行根目录（数据落在它下面）"""
    return ROOT


STATIC_DIR = os.path.join(RES, 'frontend')
PACK_PATH = os.path.join(RES, 'resources', 'arknights.json')
PARADOX_PATH = os.path.join(RES, 'resources', 'paradox.json')

CONFIG_DIR = os.path.join(ROOT, 'config')
SKLAND_DIR = os.path.join(CONFIG_DIR, 'skland')
ACCOUNTS_DIR = os.path.join(SKLAND_DIR, 'accounts')
SETTINGS_PATH = os.path.join(CONFIG_DIR, 'settings.json')
DEBUG_DIR = os.path.join(ROOT, 'debug')
LOG_PATH = os.path.join(DEBUG_DIR, 'app.log')


def _migrate_legacy_log():
    """旧日志在 config/app.log，挪进 debug/（新位置已有同名文件则不动）"""
    for name in ('app.log', 'app.log.1'):
        src, dst = os.path.join(CONFIG_DIR, name), os.path.join(DEBUG_DIR, name)
        if os.path.isfile(src) and not os.path.isfile(dst):
            try:
                os.makedirs(DEBUG_DIR, exist_ok=True)
                os.replace(src, dst)
            except Exception:
                pass


def _migrate_legacy_skland():
    """旧版账号数据在 <项目根>/skland/，启动时并入 config/skland/

    只搬文件不动内容：tokens.txt 的加密转换在 accounts.load_tokens() 里做。
    新位置已有同名文件时跳过（宁可不搬也不覆盖），目录搬空才删。
    """
    old = os.path.join(ROOT, 'skland')
    if not os.path.isdir(old) or os.path.abspath(old) == os.path.abspath(SKLAND_DIR):
        return
    import shutil
    os.makedirs(SKLAND_DIR, exist_ok=True)
    for name in os.listdir(old):
        src, dst = os.path.join(old, name), os.path.join(SKLAND_DIR, name)
        if os.path.exists(dst):
            continue
        try:
            shutil.move(src, dst)
        except Exception:
            pass
    # 搬空了才删目录；README.md 是旧版的入库说明，一并清掉（新版文档在 docs/）
    try:
        left = [n for n in os.listdir(old) if n != 'README.md']
        if not left:
            for n in os.listdir(old):
                os.remove(os.path.join(old, n))
            os.rmdir(old)
    except Exception:
        pass


try:
    _migrate_legacy_skland()
    _migrate_legacy_log()
except Exception:
    pass

for _d in (SKLAND_DIR, ACCOUNTS_DIR, CONFIG_DIR, DEBUG_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except Exception:
        pass

DEFAULTS = {
    'maaDir': '',
    'maaDirs': [],          # 用过的 MAA 根目录历史（添加账号时「已存过」列表的数据源）
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


def _norm_dir(v: str) -> str:
    """容忍从资源管理器粘来的路径：正反斜杠混用、末尾带斜杠、双斜杠"""
    v = (v or '').strip().strip('"')
    if not v:
        return ''
    v = os.path.normpath(v.replace('/', '\\'))
    if v.endswith('\\') and len(v) > 3:
        v = v.rstrip('\\')
    return v


def _merged_dirs(dirs, extra):
    """历史目录列表并入一个新目录（过滤脏值，大小写不敏感去重）"""
    out = [d for d in (dirs or []) if isinstance(d, str) and d]
    if extra and os.path.normcase(extra) not in {os.path.normcase(d) for d in out}:
        out.append(extra)
    return out


def remember_maa_dir(d: str) -> None:
    """把一个 MAA 根目录并入 maaDirs 历史（账号绑定与全局保存共用入口）"""
    d = _norm_dir(d)
    if not d:
        return
    with _lock:
        save({'maaDirs': _merged_dirs(load().get('maaDirs'), d)})


def save(patch: dict) -> dict:
    global _cache
    with _lock:
        cur = load()
        for k, v in (patch or {}).items():
            if k not in DEFAULTS:
                continue
            if k == 'maaDir':
                v = _norm_dir(v)
            cur[k] = v
        # maaDir 每次保存都并入历史列表（大小写不敏感去重）
        if cur.get('maaDir'):
            cur['maaDirs'] = _merged_dirs(cur.get('maaDirs'), cur['maaDir'])
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
    """加密的 token 存储（内容经 Windows DPAPI 加密，见 core/vault.py）"""
    return os.path.join(SKLAND_DIR, 'tokens.json')


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


def paradox_path() -> str:
    """悖论模拟清单路径（与 pack_path 同样的覆盖规则）"""
    local = os.path.join(ROOT, 'resources', 'paradox.json')
    if os.path.isfile(local):
        return local
    return PARADOX_PATH
