# -*- coding: utf-8 -*-
"""MAA 集成：进程控制、配置读写、作业写入"""
from __future__ import annotations

import copy
import io
import json
import os
import re
import shutil
import subprocess
import time

from . import copilot, settings, tasks

CREATE_NO_WINDOW = 0x08000000
SAFE = re.compile(r'[\\/:*?"<>|]')

# 每次写入作业都会备份一份 gui.new.json，只保留最近几份，避免占满用户磁盘
KEEP_BACKUPS = 2
BACKUP_PREFIX = '.bak-app-'
BACKUP_STAMP = re.compile(r'^\d{8}-\d{6}$')


def _dir():
    return settings.load()['maaDir']


def _exe():
    return os.path.join(_dir(), 'MAA.exe')


def _config_path():
    return os.path.join(_dir(), 'config', 'gui.new.json')


def _copilot_dir():
    return os.path.join(_dir(), 'config', 'copilot')


def _prune_backups(keep=KEEP_BACKUPS):
    """清理本程序生成的 .bak-app-<时间戳>，只留最近 keep 份

    只认「gui.new.json.bak-app-YYYYMMDD-HHMMSS」这种自己写出来的名字，
    用户或 MAA 自己的 .bak / .bak-auto / .bak-before-xxx 一律不碰。
    返回被删掉的文件名列表。
    """
    cfg = _config_path()
    folder = os.path.dirname(cfg)
    prefix = os.path.basename(cfg) + BACKUP_PREFIX
    try:
        names = os.listdir(folder)
    except OSError:
        return []

    cand = [n for n in names
            if n.startswith(prefix) and BACKUP_STAMP.match(n[len(prefix):])]
    if len(cand) <= keep:
        return []

    cand.sort(reverse=True)          # 时间戳定长，字典序即时间序
    removed = []
    for name in cand[keep:]:
        try:
            os.remove(os.path.join(folder, name))
            removed.append(name)
        except OSError:
            pass
    return removed


def _load_cfg():
    p = _config_path()
    if not os.path.isfile(p):
        raise FileNotFoundError('找不到 MAA 配置：%s（设置里检查 MAA 根目录）' % p)
    with io.open(p, encoding='utf-8') as f:
        return json.load(f)


def _save_cfg(data):
    p = _config_path()
    tmp = p + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp, p)


# ---------------------------------------------------------------- 状态
def is_running() -> bool:
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq MAA.exe', '/NH'],
                             capture_output=True, timeout=8,
                             creationflags=CREATE_NO_WINDOW)
        return b'maa.exe' in out.stdout.lower()
    except Exception:
        return False


def list_running():
    """列出正在运行的 MAA.exe，从进程反查安装目录（首次引导用）。

    tasklist 只告诉有没有、不给路径，起 PowerShell 又慢，直接
    Toolhelp32 快照 + QueryFullProcessImageNameW 拿完整路径。
    同目录多开只留一条，pid 合并展示。
    """
    import ctypes
    import ctypes.wintypes as wintypes

    class PE32W(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_wchar * 260),
        ]

    TH32CS_SNAPPROCESS = 0x2
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_wchar_p, ctypes.c_void_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.CloseHandle.restype = wintypes.BOOL

    def image_path(pid):
        """exe 完整路径；权限不够（别的用户的进程）拿不到就返回 None"""
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = wintypes.DWORD(len(buf))
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return buf.value
            return None
        finally:
            k32.CloseHandle(h)

    found = {}
    try:
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap or snap == ctypes.c_void_p(-1).value:
            return []
        try:
            ent = PE32W()
            ent.dwSize = ctypes.sizeof(PE32W)
            ok = k32.Process32FirstW(snap, ctypes.byref(ent))
            while ok:
                if ent.szExeFile.lower() == 'maa.exe':
                    p = image_path(ent.th32ProcessID)
                    if p:
                        row = found.setdefault(p.lower(), {'path': p, 'dir': os.path.dirname(p), 'pids': []})
                        row['pids'].append(ent.th32ProcessID)
                ok = k32.Process32NextW(snap, ctypes.byref(ent))
        finally:
            k32.CloseHandle(snap)
    except Exception:
        return []
    out = sorted(found.values(), key=lambda r: r['dir'])
    return out


def status():
    d = _dir()
    cfg_ok = os.path.isfile(_config_path())
    profiles, current = [], None
    if cfg_ok:
        try:
            cfg = _load_cfg()
            profiles = list((cfg.get('Configurations') or {}).keys())
            current = cfg.get('Current')
        except Exception:
            cfg_ok = False
    return {
        'maaDir': d,
        'exeExists': os.path.isfile(_exe()),
        'configExists': cfg_ok,
        'running': is_running(),
        'profiles': profiles,
        'current': current,
        'profile': settings.load()['profile'],
    }


def close():
    if is_running():
        subprocess.run(['taskkill', '/IM', 'MAA.exe', '/F'],
                       capture_output=True, timeout=15, creationflags=CREATE_NO_WINDOW)
        for _ in range(20):
            if not is_running():
                return True
            time.sleep(0.3)
    return not is_running()


def launch():
    exe = _exe()
    if not os.path.isfile(exe):
        raise FileNotFoundError('找不到 MAA.exe：%s' % exe)
    subprocess.Popen([exe], cwd=_dir(), close_fds=True)
    time.sleep(1.0)
    return is_running()


# ---------------------------------------------------------------- 写作业
def _safe(name):
    return SAFE.sub('_', name).strip() or 'stage'


def apply_plan(items, profile=None, mode='replace', auto_start=True, tid=None):
    """items: [{copilotId, stageCode, title}] → 写入 MAA 多作业列表"""
    log = tasks.log_factory(tid) if tid else (lambda *_: None)
    profile = profile or settings.load()['profile']

    log('MAA 目录：%s' % _dir())
    if is_running():
        log('检测到 MAA 正在运行，先关闭…')
        close()
        log('MAA 已关闭')
    else:
        log('MAA 未运行')

    time.sleep(0.4)
    bak = _config_path() + BACKUP_PREFIX + time.strftime('%Y%m%d-%H%M%S')
    shutil.copyfile(_config_path(), bak)
    log('配置已备份 → %s' % os.path.basename(bak))
    dropped = _prune_backups()
    if dropped:
        log('清理旧备份 %d 个（只保留最近 %d 份）' % (len(dropped), KEEP_BACKUPS))

    cfg = _load_cfg()
    configs = cfg.get('Configurations') or {}
    if profile not in configs:
        raise ValueError('配置「%s」不存在，可选：%s' % (profile, ', '.join(configs)))

    tpl = copy.deepcopy((configs.get('Default') or {}).get('Copilot') or {})
    target = configs[profile]
    cop = target.get('Copilot') or {}
    for k, v in tpl.items():
        cop.setdefault(k, copy.deepcopy(v))

    old = list(cop.get('TaskList') or []) if mode == 'append' else []
    new_entries, files = [], []
    cache = {}                      # copilotId → (文件名, flags)，同一份作业被普通/突袭两行各加一次时不重复下载

    for idx, it in enumerate(items, 1):
        cid = int(it['copilotId'])
        stage_code = it.get('stageCode') or str(cid)
        if cid in cache:
            fname, flags = cache[cid]
            log('[%d/%d] 复用已下载的作业 #%s %s' % (idx, len(items), cid, it.get('title') or ''))
        else:
            log('[%d/%d] 下载作业 #%s %s' % (idx, len(items), cid, it.get('title') or ''))
            content = copilot.download_content(cid)
            content, notes = copilot.normalize_for_maa(content)
            for n in notes:
                log('    修正：%s' % n)
            flags = copilot.difficulty_flags(content)
            fname = '%s_%s.json' % (_safe(stage_code), cid)
            os.makedirs(_copilot_dir(), exist_ok=True)
            fpath = os.path.join(_copilot_dir(), fname)
            with io.open(fpath, 'w', encoding='utf-8') as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            cache[cid] = (fname, flags)
        if fname not in files:
            files.append(fname)

        # 作业集里带 variant 的条目是从「普通 / 突袭」那一行加的，只写对应那一条，
        # 这样同一关可以分别挑一份普通作业和一份突袭作业；不带 variant 的（卡片、
        # 详情弹窗）沿用 MAA 的做法，按作业自己的难度标志展开。
        raids = copilot.entry_variants(flags, it.get('variant'))
        for is_raid in raids:
            new_entries.append({
                # Name 只是 MAA 列表里的标签，用可读的名字（悖论关卡就是「悖论·仇白」），
                # 没给名字的仍然退回关卡代号
                'Name': it.get('name') or stage_code,
                'IsNavNameOverride': False,
                'FilePath': 'config\\copilot\\' + fname,
                'CopilotId': cid,
                'IsRaid': is_raid,
                'IsChecked': True,
                'Index': 0,
            })
        log('    难度：%s → 写入 %s' % (
            copilot.difficulty_text(flags),
            ' + '.join('突袭' if r else '普通' for r in raids) or '无'))

    task_list = old + new_entries
    for i, t in enumerate(task_list):
        t['Index'] = i
    cop['TaskList'] = task_list
    target['Copilot'] = cop
    cfg.setdefault('Configurations', {})[profile] = target
    if 'Current' in cfg:
        cfg['Current'] = profile
    _save_cfg(cfg)
    log('已写入配置「%s」，作业列表 %d 条（本次新增 %d）' % (profile, len(task_list), len(new_entries)))

    started = False
    if auto_start:
        log('启动 MAA…')
        try:
            started = launch()
            log('MAA 已启动' if started else 'MAA 启动后未检测到进程，请手动打开')
        except Exception as e:
            log('启动失败：%s' % e)

    return {'profile': profile, 'taskCount': len(task_list),
            'added': len(new_entries), 'files': files, 'started': started}


def start_apply(items, profile=None, mode='replace', auto_start=True):
    title = '写入 MAA（%d 份作业）' % len(items or [])
    holder = {}

    def go():
        try:
            res = apply_plan(items, profile, mode, auto_start, holder['tid'])
            tasks.finish(holder['tid'], result=res)
        except Exception as e:
            import traceback
            tasks.finish(holder['tid'], error='%s: %s' % (type(e).__name__, e),
                         result={'traceback': traceback.format_exc()})

    import threading
    tid = tasks.create(title, None)
    holder['tid'] = tid
    threading.Thread(target=go, daemon=True).start()
    return tid


def clear_tasklist(profile=None):
    cfg = _load_cfg()
    profile = profile or settings.load()['profile']
    configs = cfg.get('Configurations') or {}
    if profile not in configs:
        raise ValueError('配置不存在：%s' % profile)
    configs[profile].setdefault('Copilot', {})['TaskList'] = []
    _save_cfg(cfg)
    return True


def tasklist(profile=None):
    cfg = _load_cfg()
    profile = profile or cfg.get('Current') or settings.load()['profile']
    cop = ((cfg.get('Configurations') or {}).get(profile) or {}).get('Copilot') or {}
    return {'profile': profile, 'items': cop.get('TaskList') or []}
