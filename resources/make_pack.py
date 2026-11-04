# -*- coding: utf-8 -*-
"""把 ArknightsGameResource 的 excel 表压成一个内置资源包

用途：MAA-PRTS 需要干员名、星级、职业、技能名、模组名、关卡表来本地完成
     「缺卡计算」和「关卡代号 → stage_id」的换算。原始 excel 表合计 50 MB，
     直接塞进仓库太重，这里只保留用得到的字段，压到 1 MB 以内。

用法：
    python resources/make_pack.py --excel "D:\\ArknightsGameResource\\gamedata\\excel"
    python resources/make_pack.py --excel ... --out resources/arknights.json
    python resources/make_pack.py --excel ... --subprof skland/subprof_cache.json

只在游戏大版本更新后需要重跑一次；平时程序只读 arknights.json，不碰原始表。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path, default=None):
    try:
        with io.open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def build(excel_dir, subprof_path=None):
    chars_src = load(os.path.join(excel_dir, 'character_table.json')) or {}
    patch = (load(os.path.join(excel_dir, 'char_patch_table.json')) or {}).get('patchChars') or {}
    skills_src = load(os.path.join(excel_dir, 'skill_table.json')) or {}
    equips_src = (load(os.path.join(excel_dir, 'uniequip_table.json')) or {}).get('equipDict') or {}
    stages_src = (load(os.path.join(excel_dir, 'stage_table.json')) or {}).get('stages') or {}
    zones_src = (load(os.path.join(excel_dir, 'zone_table.json')) or {}).get('zones') or {}

    if not chars_src:
        raise SystemExit('character_table.json 读不到，检查 --excel 路径：%s' % excel_dir)

    chars = {}
    for cid, v in list(chars_src.items()) + list(patch.items()):
        if not cid.startswith('char_'):
            continue
        chars[cid] = {
            'name': v.get('name') or cid,
            'rarity': int(v.get('rarity') or 0),          # 0 基，6 星 = 5
            'profession': v.get('profession') or '',
            'subProfessionId': v.get('subProfessionId') or '',
            'isNotObtainable': bool(v.get('isNotObtainable')),
        }

    skills = {}
    for sid, s in skills_src.items():
        levels = s.get('levels') or []
        name = (levels[0].get('name') if levels else '') or s.get('skillName') or ''
        if name:
            skills[sid] = name

    equips = {}
    for eid, e in equips_src.items():
        equips[eid] = {
            'uniEquipName': e.get('uniEquipName') or eid,
            'typeIcon': e.get('typeIcon') or '',
        }

    stages = []
    for sid, st in stages_src.items():
        code = st.get('code') or ''
        if not code:
            continue
        stages.append({
            'id': sid,
            'code': code,
            'name': st.get('name') or '',
            'zone': st.get('zoneId') or '',
        })
    stages.sort(key=lambda r: r['id'])

    zones = {}
    for zid, z in zones_src.items():
        zones[zid] = {
            'name': z.get('zoneNameSecond') or z.get('zoneNameFirst') or '',
            'type': z.get('type') or '',
        }

    # 分支中文名没有官方静态表，只能从森空岛接口学；把已学到的带进包里当种子
    subprof = {}
    if subprof_path and os.path.isfile(subprof_path):
        subprof = load(subprof_path) or {}

    counts = {
        'chars': len(chars),
        'skills': len(skills),
        'equips': len(equips),
        'stages': len(stages),
        'zones': len(zones),
        'subProfessions': len(subprof),
    }
    now = dt.datetime.now().astimezone()
    version = now.strftime('%Y.%m.%d')
    # 内容指纹：同一天重复生成也能区分（程序侧靠它判断资源有没有变）
    fingerprint = hashlib.sha1(
        json.dumps([version, counts, [s['id'] for s in stages]],
                   sort_keys=True).encode('utf-8')
    ).hexdigest()[:8]

    return {
        'schema': 1,
        'version': version,
        'fingerprint': fingerprint,
        'generatedAt': now.isoformat(timespec='seconds'),
        'source': 'ArknightsGameResource/gamedata/excel',
        'counts': counts,
        'chars': chars,
        'skills': skills,
        'equips': equips,
        'stages': stages,
        'zones': zones,
        'subProfessions': subprof,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description='生成内置游戏资源包')
    ap.add_argument('--excel', required=True, help='ArknightsGameResource/gamedata/excel 目录')
    ap.add_argument('--out', default=os.path.join(HERE, 'arknights.json'))
    ap.add_argument('--subprof', default=os.path.join(os.path.dirname(HERE), 'skland', 'subprof_cache.json'))
    args = ap.parse_args(argv)

    pack = build(args.excel, args.subprof)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    tmp = args.out + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(pack, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, args.out)

    size = os.path.getsize(args.out) / 1024 / 1024
    print('已生成：%s（%.2f MB）' % (args.out, size))
    for k, v in pack['counts'].items():
        print('  %-16s %d' % (k, v))
    return 0


if __name__ == '__main__':
    sys.exit(main())
