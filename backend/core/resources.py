# -*- coding: utf-8 -*-
"""内置游戏资源包：关卡索引、活动名、干员表、技能名、模组名

数据来自 resources/arknights.json（由 make_pack.py 从 ArknightsGameResource 压出来），
程序运行时不依赖任何外部游戏目录，也就不需要用户额外准备资源表。
"""
from __future__ import annotations

import io
import json
import re
import threading

from . import settings

_lock = threading.RLock()
_cache = {}
_pack_cache = [None]


def pack() -> dict:
    """资源包（整个进程只读一次）"""
    with _lock:
        if _pack_cache[0] is None:
            try:
                with io.open(settings.pack_path(), encoding='utf-8') as f:
                    _pack_cache[0] = json.load(f)
            except Exception:
                _pack_cache[0] = {'chars': {}, 'skills': {}, 'equips': {},
                                  'stages': [], 'zones': {}, 'subProfessions': {}, 'counts': {}}
        return _pack_cache[0]


def pack_info() -> dict:
    p = pack()
    return {
        'version': p.get('version') or '',
        'fingerprint': p.get('fingerprint') or '',
        'generatedAt': p.get('generatedAt'),
        'counts': p.get('counts') or {},
        'path': settings.pack_path(),
    }


def _stages():
    with _lock:
        if 'stages' in _cache:
            return _cache['stages']
        p = pack()
        zones = p.get('zones') or {}
        rows = []
        for st in p.get('stages') or []:
            zid = st.get('zone') or ''
            zone = zones.get(zid) or {}
            rows.append({
                'stageId': st['id'],
                'code': st.get('code') or '',
                'name': st.get('name') or '',
                'zoneId': zid,
                'zoneName': zone.get('name') or '',
                'zoneType': zone.get('type') or '',
                'difficulty': '',
                'danger': '',
            })
        rows.sort(key=lambda r: (r['stageId'], r['code']))
        _cache['stages'] = rows
        return rows


def _norm(s):
    return re.sub(r'\s+', '', str(s or '')).lower()


def resolve(keyword: str) -> dict:
    """把用户输入解析成关卡列表

    返回 {mode:'stage'|'activity'|'unknown', title, keyword, stages:[...]}
    支持：TL-10 / act55side_10 / TR- / act55side / 中文关卡名 / 中文活动名
    """
    kw = (keyword or '').strip()
    if not kw:
        return {'mode': 'unknown', 'title': '', 'keyword': kw, 'stages': []}

    stages = _stages()
    low = kw.lower()

    # 1. 关卡代号精确（TL-10、TR-1、1-7）
    hit = [s for s in stages if s['code'].lower() == low]
    if hit:
        return {'mode': 'stage', 'title': hit[0]['code'] + ' ' + hit[0]['name'],
                'keyword': kw, 'stages': hit[:1]}

    # 2. 关卡内部 id 精确（act55side_10）
    hit = [s for s in stages if s['stageId'].lower() == low]
    if hit:
        return {'mode': 'stage', 'title': hit[0]['code'] + ' ' + hit[0]['name'],
                'keyword': kw, 'stages': hit[:1]}

    # 3. 关卡代号前缀（TR- → 全部 TR 关，排除塔模式重名关）
    hit = [s for s in stages
           if s['code'].lower().startswith(low) and re.search(r'\d', s['code'])
           and not s['stageId'].startswith('lt_')
           and not s['zoneId'].startswith('tower')]
    if hit:
        hit.sort(key=lambda r: (len(r['code']), r['code']))
        return {'mode': 'activity', 'title': '%s 系列（%d 关）' % (kw.upper(), len(hit)),
                'keyword': kw, 'stages': hit}

    # 4. 活动内部 id 前缀（act55side → 该活动全部关卡）
    hit = [s for s in stages if s['stageId'].lower().startswith(low) and '_' in s['stageId']]
    if hit:
        zone_name = ''
        for s in hit:
            if s['zoneName']:
                zone_name = s['zoneName']
                break
        return {'mode': 'activity',
                'title': '%s（%d 关）' % (zone_name or kw, len(hit)),
                'keyword': kw, 'stages': hit}

    # 5. 中文活动名 / 关卡名模糊
    n = _norm(kw)
    hit = [s for s in stages if n and n in _norm(s['zoneName'])]
    if not hit:
        hit = [s for s in stages if n and n in _norm(s['name'])]
    if hit:
        if len(hit) == 1:
            return {'mode': 'stage', 'title': hit[0]['code'] + ' ' + hit[0]['name'],
                    'keyword': kw, 'stages': hit[:1]}
        return {'mode': 'activity', 'title': '%s（%d 关）' % (kw, len(hit)),
                'keyword': kw, 'stages': hit}

    return {'mode': 'unknown', 'title': '', 'keyword': kw, 'stages': []}


def activity_list(limit: int = 16) -> list:
    """近期活动（按 act 编号倒序），给前端做快捷入口

    每条带 prefix（关卡代号字母，残照终尽 → TL），前端把它显示在活动名后面，
    用户一眼就知道这个活动搜什么代号。
    """
    groups = {}
    for s in _stages():
        sid = s['stageId']
        if not sid.startswith('act'):
            continue
        m = re.match(r'act(\d+)', sid)
        if not m:
            continue
        key = sid.split('_')[0]
        g = groups.get(key)
        if g is None:
            g = groups[key] = {'id': key, 'num': int(m.group(1)),
                               'name': '', 'count': 0, 'codes': []}
        g['count'] += 1
        if s['code']:
            g['codes'].append(s['code'])
        if s['zoneName'] and not g['name']:
            g['name'] = s['zoneName']

    rows = sorted(groups.values(), key=lambda r: -r['num'])[:limit]
    out = []
    for r in rows:
        if r['count'] < 3:
            continue
        out.append({
            'id': r['id'],
            'num': r['num'],
            'name': r['name'] or r['id'],
            'prefix': _code_prefix(r['codes']),
            'count': r['count'],
        })
    return out


def _code_prefix(codes) -> str:
    """从关卡代号里取活动的字母前缀：TL-1..TL-EX-8 → TL"""
    hits = {}
    for c in codes or []:
        m = re.match(r'^([A-Za-z]{1,4})[-\d]', c)
        if m:
            p = m.group(1).upper()
            hits[p] = hits.get(p, 0) + 1
    if not hits:
        return ''
    return max(hits.items(), key=lambda kv: kv[1])[0]


def char_table() -> dict:
    return pack().get('chars') or {}


def skill_table() -> dict:
    return pack().get('skills') or {}


def equip_table() -> dict:
    return pack().get('equips') or {}


def subprof_seed() -> dict:
    """资源包里附带的分支中文名种子（分支名没有公开静态表，只能边用边学）"""
    return pack().get('subProfessions') or {}


def clear_cache():
    with _lock:
        _cache.clear()
        _pack_cache[0] = None
