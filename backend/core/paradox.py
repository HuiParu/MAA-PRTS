# -*- coding: utf-8 -*-
"""悖论模拟：从账号练度推算「哪些能打」，再按关卡去作业站取作业

为什么不用截图识别：
  森空岛的 /player/info 没有悖论字段，但 handbookStageData 的解锁条件只有
  「精英化阶段 + 等级」两项，而账号快照里每个干员的 elite / level 都有。
  所以「哪些悖论能开打」可以完全推算出来，不需要读图，也就不需要把
  立绘/头像压进包里。

  实测过纯图匹配（头像 dHash、立绘多尺度对齐），同一账号 12 张卡片只能命中
  8 张——玩家穿皮肤、每张画构图不同，识别率不够做产品，已放弃。

练度只校验「悖论对应的那个干员」：悖论关卡是官方给的固定阵容，其它干员的
requirements 与玩家无关。
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import copilot, settings

_lock = threading.RLock()
_cache = {'data': None, 'mtime': 0}

SCHEMA = 2


def table() -> dict:
    """内置悖论清单（进程内只读一次，文件换了自动重载）"""
    path = settings.paradox_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    with _lock:
        if _cache['data'] is not None and _cache['mtime'] == mtime:
            return _cache['data']
        try:
            with io.open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {'schema': SCHEMA, 'count': 0, 'chars': {}}
        data.setdefault('chars', {})
        _cache['data'] = data
        _cache['mtime'] = mtime
        return data


def info() -> dict:
    d = table()
    return {
        'count': d.get('count') or len(d.get('chars') or {}),
        'generatedAt': d.get('generatedAt') or '',
        'gameVersion': d.get('gameVersion') or '',
        'schema': d.get('schema'),
    }


# ---------------------------------------------------------------- 推算
def _unlocked(char, entry) -> bool:
    if not char:
        return False
    return (int(char.get('elite') or 0) >= int(entry.get('elite') or 0)
            and int(char.get('level') or 0) >= int(entry.get('level') or 0))


def _imported(snap) -> dict:
    return ((snap.get('paradox') or {}).get('imported') or {})


def plan(snap) -> dict:
    """当前账号的悖论清单

    返回的每一项都带 `ready`（练度够不够开打）和 `imported`（以前导入过没有），
    UI 默认只勾「ready 且没导入过」的那些。
    """
    chars = {}
    for c in snap.get('chars') or []:
        cid = c.get('charId')
        if cid:
            chars[cid] = c
    done = _imported(snap)

    items, not_owned = [], 0
    for cid, e in (table().get('chars') or {}).items():
        c = chars.get(cid)
        if not c:
            not_owned += 1
            continue
        stage = e.get('stage') or ''
        ready = _unlocked(c, e)
        items.append({
            'charId': cid,
            'name': e.get('name') or c.get('name') or cid,
            'stage': stage,
            'pname': e.get('pname') or '',
            'rarity': int(c.get('rarity') or 0),
            'profession': c.get('profession') or '',
            'elite': int(c.get('elite') or 0),
            'level': int(c.get('level') or 0),
            'needElite': int(e.get('elite') or 0),
            'needLevel': int(e.get('level') or 0),
            'ready': ready,
            'imported': bool(done.get(stage)),
            'importedAt': done.get(stage) or '',
        })

    # 能打的排前面；同档按稀有度、精英、等级、名字排，和游戏里「悖论模拟」筛选后的手感接近
    items.sort(key=lambda r: (not r['ready'], -r['rarity'], -r['elite'], -r['level'], r['name']))
    ready = [r for r in items if r['ready']]
    todo = [r for r in ready if not r['imported']]
    return {
        'items': items,
        'stats': {
            'total': len(items) + not_owned,
            'owned': len(items),
            'ready': len(ready),
            'locked': len(items) - len(ready),
            'notOwned': not_owned,
            'imported': len(ready) - len(todo),
            'todo': len(todo),
        },
        'table': info(),
    }


# ---------------------------------------------------------------- 作业
def stage_jobs(stage: str, limit=8) -> list:
    """作业站里某个悖论关卡（mem_xxx_1）的作业，按热度/评分排"""
    if not stage:
        return []
    stage_info = {'stageId': stage, 'code': stage, 'name': stage}
    try:
        items = copilot.fetch_ops(stage_info, pages=1, min_rating=0)
    except Exception:
        return []
    rows = []
    for it in items:
        meta, content = it['meta'], it['content']
        doc = content.get('doc') or {}
        rows.append({
            'copilotId': meta.get('id'),
            'title': doc.get('title') or '(无标题)',
            'rating': meta.get('rating_level') or 0,
            'views': meta.get('views') or 0,
            'opers': len(content.get('opers') or []),
            'difficulty': copilot.difficulty_flags(content),
            'uploader': meta.get('uploader') or doc.get('uploader') or '',
            'content': content,
        })
    rows.sort(key=lambda r: (-r['rating'], -r['views']))
    return rows


def pick(stages, snap=None, limit=12) -> dict:
    """批量取「每关最合适的一份作业」，给作业集用

    不校验作业里别的干员练度：悖论关卡是官方固定阵容，玩家自己的干员只是
    「解锁条件」——练度够不够开打已经在 plan() 里判过了（ready）。
    """
    wanted = [s for s in (stages or []) if s]

    def one(stage):
        rows = stage_jobs(stage, limit=limit)
        if not rows:
            return {'stage': stage, 'ok': False, 'reason': '作业站没有这一关的作业'}
        r = rows[0]
        return {
            'stage': stage, 'ok': True,
            'copilotId': r['copilotId'], 'title': r['title'],
            'rating': r['rating'], 'views': r['views'],
            'difficulty': r['difficulty'],
            'difficultyText': copilot.difficulty_text(r['difficulty']),
            'opers': r['opers'], 'candidates': len(rows),
        }

    workers = min(6, max(1, len(wanted)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        got = list(ex.map(one, wanted))

    ok = [g for g in got if g['ok']]
    return {'ok': ok, 'failed': [g for g in got if not g['ok']]}


# ---------------------------------------------------------------- 已导入标记
def mark_imported(snap, stages) -> dict:
    """记下「这些悖论已经排进 MAA 作业集」，下次默认不勾"""
    sec = snap.setdefault('paradox', {})
    imp = sec.setdefault('imported', {})
    stamp = time.strftime('%Y-%m-%d %H:%M')
    for s in stages or []:
        if s:
            imp[s] = stamp
    sec['updatedAt'] = stamp
    return imp
