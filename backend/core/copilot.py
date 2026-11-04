# -*- coding: utf-8 -*-
"""作业站（prts.plus）搜索 + 干员匹配

匹配算法复刻作业站前端 models/operatorMatcher.ts：
    练度：把「精英阶段 + 等级」折算成进度分再比较（不是逐项死比）
    技能：requirements.skill_level >= 8 看专精（10 = 专三），否则看技能等级 1~7
    模组：module > 0 时只要求该模组已解锁（等级 >= 1）
    人数：> 13 人或缺 2 人以上 → blocked
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import resources, settings

API = 'https://prts.maa.plus/copilot'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) MAA-PRTS/1.0'}

MAX_LEVELS = {0: (30, 0, 0), 1: (30, 0, 0), 2: (30, 0, 0), 3: (40, 55, 0),
              4: (45, 60, 70), 5: (50, 70, 80), 6: (50, 80, 90)}

MODES = ('ready', 'borrow', 'train', 'blocked')
MODE_CN = {'ready': '可直接抄', 'borrow': '差一人可借', 'train': '需补练度', 'blocked': '打不了'}

_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 600


def _http_json(url, timeout=40, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            if i == retries - 1:
                raise
            time.sleep(1.2 * (i + 1))
    raise last


def _query(**params):
    p = {'page': 1, 'limit': 50, 'orderBy': 'hot', 'desc': 'true'}
    p.update({k: v for k, v in params.items() if v is not None})
    url = API + '/query?' + urllib.parse.urlencode(p)
    d = _http_json(url)
    return (d or {}).get('data') or {}


def norm(name):
    return re.sub(r'\s+', '', str(name or ''))


# ---------------------------------------------------------------- 匹配
def progress_score(rarity, elite, level):
    lv = MAX_LEVELS.get(int(rarity or 6), MAX_LEVELS[6])
    score = max(1, int(level or 0))
    for i in range(int(elite or 0)):
        score += lv[i] if i < len(lv) else 0
    return score


def infer_elite(rarity, level, elite):
    if elite is not None:
        return int(elite)
    lv = MAX_LEVELS.get(int(rarity or 6), MAX_LEVELS[6])
    e = 0
    while e < len(lv) - 1 and int(level or 0) > lv[e]:
        e += 1
    return e


def req_met(req, owned):
    """req 是作业里的干员条目，requirements 是它的练度要求。
    注意：技能序号 `skill` 在条目顶层，不在 requirements 里。"""
    r = req.get('requirements') or {}
    if not r:
        return True
    elite, level = r.get('elite'), r.get('level')
    if elite is not None or level is not None:
        rl = int(level or 1)
        re_ = infer_elite(owned['rarity'], rl, elite)
        if progress_score(owned['rarity'], owned['elite'], owned['level']) < \
                progress_score(owned['rarity'], re_, rl):
            return False
    sl = r.get('skill_level', r.get('skillLevel'))
    if sl is not None:
        sl = int(sl)
        if sl >= 8:
            idx = int(req.get('skill') or r.get('skill') or 1) - 1
            mv = owned['masteryLevels'][idx] if 0 <= idx < len(owned['masteryLevels']) else None
            if mv is None or mv < sl - 7:
                return False
        elif int(owned.get('mainSkillLevel') or 0) < sl:
            return False
    module = r.get('module')
    if module is not None and int(module) > 0:
        if owned['moduleLevels'].get(int(module), 0) < 1:
            return False
    return True


def _group_ok(group, owned_map):
    cands = [c for c in (group.get('opers') or []) if norm(c.get('name')) in owned_map]
    if any(req_met(c, owned_map[norm(c.get('name'))]) for c in cands):
        return 'ready'
    return 'train' if cands else 'missing'


def _group_label(g):
    return g.get('name') or ' / '.join(o.get('name', '') for o in (g.get('opers') or [])) or '组合'


def match_operation(content, owned_map):
    opers = content.get('opers') or []
    groups = content.get('groups') or []
    missing, training, detail = [], [], []

    for op in opers:
        name = norm(op.get('name'))
        owned = owned_map.get(name)
        ok = bool(owned and req_met(op, owned))
        if not owned:
            missing.append(op.get('name'))
        elif not ok:
            training.append(op.get('name'))
        detail.append({
            'name': op.get('name'),
            'owned': bool(owned),
            'ok': ok,
            'elite': owned['elite'] if owned else None,
            'level': owned['level'] if owned else None,
            'mastery': owned['masteryLevels'] if owned else [],
            'req': (op.get('requirements') or {}),
            'skill': op.get('skill'),
        })

    for g in groups:
        st = _group_ok(g, owned_map)
        if st == 'missing':
            missing.append(_group_label(g))
        elif st == 'train':
            training.append(_group_label(g))
        detail.append({'name': _group_label(g), 'group': True, 'owned': st != 'missing',
                       'ok': st == 'ready'})

    total = len(opers) + len(groups)
    if total > 13 or len(missing) >= 2:
        mode = 'blocked'
    elif len(missing) == 1:
        mode = 'train' if training else 'borrow'
    elif not training:
        mode = 'borrow' if total == 13 else 'ready'
    else:
        mode = 'borrow' if (len(training) == 1 and total < 13) else 'train'
    return mode, missing, training, total, detail


# ---------------------------------------------------------------- 账号 → owned
_SLOT = {'X': 1, 'Y': 2, 'A': 3, 'D': 4}


def _module_type(equip_id):
    ic = (resources.equip_table().get(equip_id) or {}).get('typeIcon') or ''
    ic = ic.lower()
    if not ic:
        return None
    if ic == 'original':
        return 'Original'
    return {'x': 'X', 'y': 'Y', 'd': 'D', 'a': 'A'}.get(ic.rsplit('-', 1)[-1])


def build_owned(snap):
    owned = {}
    for c in snap.get('chars') or []:
        if not c.get('name'):
            continue
        mods = {}
        for m in c.get('modules') or []:
            t = _module_type(m.get('id'))
            lv = int(m.get('level') or 0)
            if t in _SLOT and lv > 0:
                mods[_SLOT[t]] = max(mods.get(_SLOT[t], 0), lv)
        owned[norm(c['name'])] = {
            'name': c['name'],
            'rarity': int(c.get('rarity') or 6),
            'elite': int(c.get('elite') or 0),
            'level': int(c.get('level') or 0),
            'mainSkillLevel': int(c.get('skillLevel') or 0),
            'masteryLevels': [int(s.get('mastery') or 0) for s in (c.get('skills') or [])],
            'moduleLevels': mods,
        }
    return owned


# ---------------------------------------------------------------- 作业
def _pull(params, pages=2, limit=50):
    """按参数翻页拉作业，返回 [{meta, content}]"""
    out, seen = [], set()
    for page in range(1, max(1, pages) + 1):
        try:
            d = _query(page=page, limit=limit, **params)
        except Exception:
            break
        rows = d.get('data') or []
        for o in rows:
            oid = o.get('id')
            if oid in seen:
                continue
            seen.add(oid)
            try:
                content = json.loads(o.get('content') or '{}')
            except Exception:
                continue
            out.append({'meta': o, 'content': content})
        if not d.get('has_next') or not rows:
            break
    return out


def fetch_ops(stage, pages=2, min_rating=0, force=False):
    """拉某个关卡的作业。

    `levelKeyword` 只对作业站认识的关卡 id 生效；对 TR-x 这类关卡会退化成
    「返回全站热门」，所以必须用 stage_name 二次校验，再退回 document 搜索。
    """
    sid = stage['stageId']
    code = stage.get('code') or sid
    key = (sid, pages, min_rating)
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and not force and now - hit[0] < CACHE_TTL:
            return hit[1]

    only = lambda rows: [r for r in rows if (r['content'].get('stage_name') or '') == sid]

    # TR / 塔关等 id 作业站不认，直接用代号搜；其余先按 id 查
    direct_by_code = sid.startswith(('tr_', 'lt_'))
    if direct_by_code:
        items = only(_pull({'document': code}, pages))
    else:
        items = only(_pull({'levelKeyword': sid}, pages))
        if not items:
            items = only(_pull({'document': code}, pages))

    items = [i for i in items if (i['meta'].get('rating_level') or 0) >= min_rating]

    with _cache_lock:
        _cache[key] = (now, items)
    return items


def _item(stage, item, mode, missing, training, total, detail):
    meta = item['meta']
    content = item['content']
    doc = content.get('doc') or {}
    return {
        'id': meta.get('id'),
        'copilotId': meta.get('id'),
        'rating': meta.get('rating_level') or 0,
        'views': meta.get('views') or 0,
        'title': doc.get('title') or '(无标题)',
        'details': (doc.get('details') or '')[:400],
        'uploader': meta.get('uploader') or doc.get('uploader') or '',
        'total': total,
        'mode': mode,
        'missing': missing,
        'training': training,
        'opers': detail,
        'maaCode': 'maa://%s' % meta.get('id'),
        'stageId': stage['stageId'],
        'stageCode': stage['code'],
        'stageName': stage['name'],
        'speed': content.get('minimum_required') or '',
    }


def rank_key(row):
    return (MODES.index(row['mode']), -row['rating'], row['total'], -row['views'])


def match_stage(stage, owned_map, pages=2, min_rating=0, limit=12):
    items = fetch_ops(stage, pages=pages, min_rating=min_rating)
    rows = []
    for it in items:
        mode, missing, training, total, detail = match_operation(it['content'], owned_map)
        rows.append(_item(stage, it, mode, missing, training, total, detail))
    rows.sort(key=rank_key)
    counts = {m: sum(1 for r in rows if r['mode'] == m) for m in MODES}
    best = rows[0] if rows else None
    return {
        'stage': stage,
        'total': len(rows),
        'counts': counts,
        'best': best,
        'ops': rows[:limit],
    }


def search(keyword, snap, pages=2, min_rating=0, limit=12):
    res = resources.resolve(keyword)
    if not res['stages']:
        # 回退：把关键词当关卡代号问作业站，用返回的 stage_name 反推
        pool = [p for p in _pull({'document': keyword.strip()}, pages=1)
                if p['content'].get('stage_name')]
        if not pool:
            return {'mode': 'unknown', 'title': '', 'keyword': keyword, 'stages': []}
        sid = pool[0]['content']['stage_name']
        stage = {'stageId': sid, 'code': keyword.strip().upper(), 'name': '',
                 'zoneId': '', 'zoneName': ''}
        res = {'mode': 'stage', 'title': '%s（%s）' % (keyword, sid),
               'keyword': keyword, 'stages': [stage]}

    owned = build_owned(snap)
    stages = res['stages']
    workers = min(8, max(1, len(stages)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(
            lambda s: match_stage(s, owned, pages=pages, min_rating=min_rating, limit=limit),
            stages))

    results.sort(key=lambda r: (r['stage'].get('stageId') or ''))
    return {
        'mode': res['mode'],
        'title': res['title'],
        'keyword': res['keyword'],
        'stages': results,
    }


def operation_detail(copilot_id):
    d = _http_json(API + '/get/%s' % copilot_id)
    data = (d or {}).get('data') or {}
    raw = data.get('content') or data.get('parsedContent') or '{}'
    content = json.loads(raw) if isinstance(raw, str) else raw
    return {'meta': data, 'content': content}


def download_content(copilot_id):
    """给 MAA 用的原始作业 json"""
    d = operation_detail(copilot_id)
    c = d['content']
    if not c.get('stage_name'):
        raise ValueError('作业 #%s 内容不完整' % copilot_id)
    return c
