# -*- coding: utf-8 -*-
"""MAA-PRTS 冒烟测试：不碰真实用户数据，全部在临时目录里跑

用法：
    .venv\\Scripts\\python.exe tools\\smoketest\\smoke_test.py
    python tools/smoketest/smoke_test.py     # 需已装运行依赖

三组检查，任何一组失败都以非 0 退出码结束：

    A. 静态检查
       - 三个 .bat 必须 UTF-8 无 BOM + CRLF 行尾（错编码会导致标签错位）
       - backend / tools / build.py 全部 .py 可编译
    B. 加密与 token 存储（隔离临时目录，monkeypatch 路径）
       - DPAPI 往返、密文篡改必报错
       - tokens.json 多账号读写、去重、备注保留
       - 旧明文 tokens.txt（三种写法）自动迁移
       - 坏密文自愈：改名 .broken 重建空列表，警告可读
       - 作业 json 交给 MAA 前的修正（非法样本必须被修成 MaaCore 能解析的样子）
    C. 启动冒烟（临时项目副本）
       - backend/main.py --no-window 拉起，解析实际端口
       - 只读接口 /api/ping、/api/bootstrap、/api/gamedata 返回 200
       - bootstrap 报告的账号数据路径在 config/skland 下
       - 结束后副本根目录除 config/ 与 debug/ 外零新增（防乱丢文件）
"""
from __future__ import annotations

import base64
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 冒烟用的只读接口
PROBE_API = ('/api/ping', '/api/bootstrap', '/api/gamedata')


class Report:
    def __init__(self):
        self.fails = 0

    def check(self, name, fn):
        try:
            fn()
        except Exception as e:
            self.fails += 1
            print('[FAIL] %s：%s: %s' % (name, type(e).__name__, e))
        else:
            print('[ ok ] %s' % name)


# ---------------------------------------------------------------- A. 静态检查
def check_bat_encoding():
    for name in ('启动.bat', '打包.bat', '调试启动.bat'):
        path = os.path.join(REPO, name)
        raw = open(path, 'rb').read()
        assert not raw.startswith(b'\xef\xbb\xbf'), '%s 带 UTF-8 BOM' % name
        assert b'\n' not in raw.replace(b'\r\n', b''), '%s 存在裸 LF 行尾' % name


def check_py_compile():
    roots = [os.path.join(REPO, 'backend'), os.path.join(REPO, 'tools')]
    files = [os.path.join(REPO, 'build.py')]
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            files += [os.path.join(dirpath, f) for f in filenames if f.endswith('.py')]
    for f in files:
        py_compile.compile(f, doraise=True)


# ---------------------------------------------------------------- B. 加密与 token 存储
def _patch_settings(tmp):
    """把 core.settings 的数据路径指到临时目录（accounts 每次调用都现取路径）"""
    sys.path.insert(0, os.path.join(REPO, 'backend'))
    from core import settings
    settings.SKLAND_DIR = os.path.join(tmp, 'skland')
    settings.ACCOUNTS_DIR = os.path.join(settings.SKLAND_DIR, 'accounts')
    return settings


def check_vault_roundtrip():
    from core import vault
    blob = vault.protect('冒烟测试 hello!@#'.encode('utf-8'))
    assert vault.unprotect(blob).decode('utf-8') == '冒烟测试 hello!@#'


def check_vault_tamper():
    from core import vault
    blob = bytearray(vault.protect(b'smoke'))
    blob[-1] ^= 0xFF
    try:
        vault.unprotect(bytes(blob))
    except OSError as e:
        m = re.search(r'错误码 (\d+)', str(e))
        assert m and int(m.group(1)) != 0, '错误码不可靠：%s' % e
        return
    raise AssertionError('篡改密文未被检出')


def check_tokens_bad_txt(tmp):
    """畸形（非 UTF-8）旧 txt：迁移失败要留证并给出警告，不能无声丢数据"""
    from core import accounts
    sk = os.path.join(tmp, 'skland')
    for f in ('tokens.json', 'tokens.txt', 'tokens.txt.bak', 'tokens.txt.broken'):
        p = os.path.join(sk, f)
        if os.path.isfile(p):
            os.remove(p)
    with open(os.path.join(sk, 'tokens.txt'), 'wb') as f:
        f.write(b'\xb1\xea\xd7\xa2:SMOKE_BAD\n')  # GBK 的「备注:」，非法 UTF-8
    items = accounts.ensure_tokens()
    assert items == [], '畸形 txt 不应产出条目'
    assert os.path.isfile(os.path.join(sk, 'tokens.txt.broken')), '坏 txt 未留证 .broken'
    assert '读取失败' in accounts.TOKENS_WARNING, '警告缺失：%s' % accounts.TOKENS_WARNING


def check_tokens_multi_account(tmp):
    from core import accounts
    accounts._save_tokens([])
    assert accounts.remember_token('SMOKE_A', '大号') is True
    assert accounts.remember_token('SMOKE_B', '小号') is True
    assert accounts.remember_token('SMOKE_C', '') is True
    assert accounts.remember_token('SMOKE_A', 'again') is False, '重复 token 未去重'
    items = accounts.load_tokens()
    assert len(items) == 3, '条目数 %d != 3' % len(items)
    assert [e['token'] for e in items] == ['SMOKE_A', 'SMOKE_B', 'SMOKE_C']
    assert items[0]['alias'] == '大号' and items[1]['alias'] == '小号'
    # 落盘文件：条目与备注可见，token 必须是密文
    env = json.load(open(os.path.join(tmp, 'skland', 'tokens.json'), encoding='utf-8'))
    assert env['version'] == 2 and env['cipher'] == 'dpapi'
    assert len(env['tokens']) == 3
    assert env['tokens'][0]['alias'] == '大号'
    assert all('SMOKE_' not in (t.get('data') or '') for t in env['tokens']), 'token 明文泄漏'


def check_tokens_migration(tmp):
    import io as _io
    from core import accounts
    sk = os.path.join(tmp, 'skland')
    os.makedirs(sk, exist_ok=True)
    for f in ('tokens.json', 'tokens.txt.bak'):
        p = os.path.join(sk, f)
        if os.path.isfile(p):
            os.remove(p)
    with _io.open(os.path.join(sk, 'tokens.txt'), 'w', encoding='utf-8') as f:
        f.write('# 注释\n'
                '大号:SMOKE_M1\n'
                '小号:SMOKE_M2:小号#1 官服.json\n'
                'SMOKE_M3\n')
    items = accounts.load_tokens()
    got = [(e['alias'], e['token']) for e in items]
    assert got == [('大号', 'SMOKE_M1'), ('小号', 'SMOKE_M2'), ('', 'SMOKE_M3')], got
    assert os.path.isfile(os.path.join(sk, 'tokens.txt.bak')), '原 txt 未留 .bak'


def check_tokens_selfheal(tmp):
    from core import accounts
    sk = os.path.join(tmp, 'skland')
    accounts._save_tokens([{'alias': 'a', 'token': 'SMOKE_H'}])
    env = json.load(open(os.path.join(sk, 'tokens.json'), encoding='utf-8'))
    env['tokens'][0]['data'] = base64.b64encode(b'garbage').decode('ascii')
    with open(os.path.join(sk, 'tokens.json'), 'w', encoding='utf-8') as f:
        json.dump(env, f)
    items = accounts.ensure_tokens()
    assert items == [], '自愈后应为空列表'
    assert os.path.isfile(os.path.join(sk, 'tokens.json.broken')), '坏文件未改名 .broken'
    assert '重新粘贴' in accounts.TOKENS_WARNING, '警告信息缺失'


def _assert_maa_parsable(content):
    """按 MaaCore CopilotConfig::parse 的致命校验复检，非法就抛 AssertionError

    对应 src/MaaCore/Config/Miscellaneous/CopilotConfig.cpp：
      parse_basic_info  读 stage_name
      parse_oper_usage  skill / skill_level / module 推出的精英要求 > 声明的 elite 直接判错
      parse_actions     Click 必须给 rect 或 location，Swipe 必须给 begin 与 end
    """
    from core import copilot

    assert content.get('stage_name'), 'stage_name 缺失'
    idx = copilot._char_index()
    opers = list(content.get('opers') or [])
    for g in (content.get('groups') or []):
        opers.extend(g.get('opers') or [])
    for op in opers:
        hit = idx.get(op.get('name') or '')
        if not hit:                       # MAA 查不到干员时跳过检查
            continue
        need = max(int(op.get('skill') or 0) - 1, 0)
        req = op.get('requirements') or {}
        sl = req.get('skill_level')
        if sl is not None:
            need = max(2 if int(sl) > 7 else (1 if int(sl) > 4 else 0), need)
        mod = req.get('module')
        if mod is not None and int(mod) > 0:
            need = max(2, need)
        if 'elite' in req and need > int(req.get('elite') or 0):
            raise AssertionError('干员 %s 需要精%d，但作业写的是精%s'
                                 % (op.get('name'), need, req.get('elite')))
    for a in (content.get('actions') or []):
        if a.get('type') == 'Click' and 'rect' not in a and 'location' not in a:
            raise AssertionError('Click 动作缺 rect/location')
        if a.get('type') == 'Swipe' and ('begin' not in a or 'end' not in a):
            raise AssertionError('Swipe 动作缺 begin/end')


def check_copilot_normalize():
    """作业站原始 json 常带非法练度要求，MaaCore 会 parse failed（作业集整体起不来）。

    这里造一份必然被 MaaCore 拒收的样本，断言 normalize_for_maa 能修成合法，
    并且修的是副本、不动调用方手里那份。
    """
    from core import copilot, resources

    chars = list((resources.char_table() or {}).values())
    low = next((c['name'] for c in chars if int(c.get('rarity') or 0) == 0), None)
    mid = next((c['name'] for c in chars if int(c.get('rarity') or 0) == 3), None)
    assert low and mid, '资源包里找不到一星/四星干员，无法构造样本'

    content = {
        'stage_name': 'smoke_01',
        'opers': [
            # 四星、技能 1、技能等级 7 → 需要精一，但写的是精 0（真实踩过的坑）
            {'name': mid, 'skill': 1, 'requirements': {'elite': 0, 'level': 45, 'skill_level': 7}},
            # 一星，没有技能 1
            {'name': low, 'skill': 1},
        ],
        'groups': [
            # 技能专精九级 → 需要精二
            {'name': 'g1', 'opers': [
                {'name': mid, 'skill': 2, 'requirements': {'elite': 0, 'skill_level': 9}}]},
        ],
        'actions': [
            {'type': 'Deploy', 'name': mid, 'location': [1, 2], 'direction': 'Right'},
            {'type': 'Skill', 'name': mid, 'location': [1, 2]},          # 名与坐标同时给
            {'type': 'Click'},                                           # 缺 rect/location
            {'type': 'Swipe', 'begin': [1, 2]},                          # 缺 end
            {'type': 'Click', 'rect': [0, 0, 10, 10], 'location': [1, 2]},
            {'type': 'UnknownType'},                                     # Core 直接跳过
        ],
        'doc': {'title': 'smoke'},
    }

    try:
        _assert_maa_parsable(content)
    except AssertionError:
        pass
    else:
        raise AssertionError('样本本身应当是 MaaCore 不接受的，测试失去意义')

    fixed, notes = copilot.normalize_for_maa(content)
    assert notes, '修正过程没有留下任何说明'
    _assert_maa_parsable(fixed)

    assert fixed['opers'][0]['requirements']['elite'] == 1, fixed['opers'][0]
    assert fixed['opers'][1]['skill'] == 0, '一星的技能 1 应被清成 0'
    assert fixed['groups'][0]['opers'][0]['requirements']['elite'] == 2

    types = [a.get('type') for a in fixed['actions']]
    assert types == ['Deploy', 'Skill', 'Click', 'UnknownType'], types
    skill = fixed['actions'][1]
    assert 'name' not in skill and 'role' not in skill, '名与坐标同时给时该清掉名字'
    click = fixed['actions'][2]
    assert 'rect' in click and 'location' not in click, 'rect 与 location 同时给时该只留 rect'
    assert fixed['actions'][0].get('name') == mid, 'Deploy 的干员名不该被清'

    # 深拷贝：调用方手里的原始内容不能被改
    assert content['opers'][0]['requirements']['elite'] == 0
    assert len(content['actions']) == 6


def check_copilot_difficulty():
    """difficulty 是位标志：0/缺失=普通、1=普通、2=突袭、3=通用

    写 MAA 时按标志拆条：通用作业要落「普通 + 突袭」两条，共用同一个作业文件。
    """
    from core import copilot

    cases = [(None, 1), (0, 1), (1, 1), (2, 2), (3, 3), ('2', 2), ('x', 1)]
    for raw, want in cases:
        got = copilot.difficulty_flags({'difficulty': raw})
        assert got == want, 'difficulty=%r 应为 %d，实际 %d' % (raw, want, got)
    assert copilot.difficulty_text(1) == '普通'
    assert copilot.difficulty_text(2) == '突袭'
    assert copilot.difficulty_text(3) == '通用'


def check_copilot_variants():
    """有突袭版的关卡拆两行：普通行只要普通可用的、突袭行只要突袭可用的

    通用作业（difficulty=3）两边都要出现；没有突袭版的关卡只出一行。
    同时确认关卡表里 #f# / #s 这类变体不会被当成独立关卡重复列出。
    """
    from core import copilot, resources

    stage = {'stageId': 'act13side_ex01', 'code': 'NL-EX-1', 'name': '都市怪谈',
             'activity': '长夜临光', 'raid': True}
    rows = [
        {'id': 1, 'difficulty': 1, 'mode': 'ready'},
        {'id': 2, 'difficulty': 2, 'mode': 'ready'},
        {'id': 3, 'difficulty': 3, 'mode': 'ready'},
        {'id': 4, 'difficulty': 3, 'mode': 'borrow'},
    ]
    normal, raid = copilot.stage_variants(stage, rows, limit=10)
    assert normal['stage']['variant'] == 'normal', '第一行应该是普通'
    assert raid['stage']['variant'] == 'raid', '第二行应该是突袭'
    assert [r['id'] for r in normal['ops']] == [1, 3, 4], \
        '普通行应含普通与通用作业，实际 %r' % [r['id'] for r in normal['ops']]
    assert [r['id'] for r in raid['ops']] == [2, 3, 4], \
        '突袭行应含突袭与通用作业，实际 %r' % [r['id'] for r in raid['ops']]
    assert normal['total'] == 3 and raid['total'] == 3
    assert normal['counts']['ready'] == 2 and raid['counts']['ready'] == 2

    # 没有突袭版的关卡只有一行，variant 固定 normal
    plain = copilot.stage_variants(dict(stage, raid=False), rows, limit=10)
    assert len(plain) == 1 and plain[0]['stage']['variant'] == 'normal', '无突袭版的关卡不该拆行'

    # 写 MAA 的条数由「加的时候在哪一行」决定，不是无脑按难度标志展开
    assert copilot.entry_variants(3, 'normal') == [False], '从普通行加通用作业只写普通'
    assert copilot.entry_variants(3, 'raid') == [True], '从突袭行加通用作业只写突袭'
    assert copilot.entry_variants(3, None) == [False, True], '不指定行时按难度展开'
    assert copilot.entry_variants(2, 'normal') == [True], '普通行里没有普通作业的兜底'
    assert copilot.entry_variants(1, 'raid') == [False]

    # 资源层：变体关不重复出现，主关带 raid 标记
    nl_ex1 = resources.resolve('NL-EX-1')['stages']
    assert len(nl_ex1) == 1, 'NL-EX-1 只应有一条，实际 %d' % len(nl_ex1)
    assert nl_ex1[0]['stageId'] == 'act13side_ex01' and nl_ex1[0]['raid'] is True
    # 粘 #f# 的 stage id 也要回落到主关
    assert resources.resolve('act13side_ex01#f#')['stages'][0]['stageId'] == 'act13side_ex01'


# ---------------------------------------------------------------- B12 v1 作业默认练度
def check_copilot_v1_default_req():
    """作业站 v1 老作业没有 requirements，练度要求未知。

    规则：没写练度的条目按星级补默认要求——六星精二60 + 专三（skill_level 9）、
    四五星精一60 + 技能7、三星精一55 + 技能7、一二星精零30 无技能。
    配置不够的号要被判成「需补练度」，不能再当成「无特殊要求」放行。
    详情里还要能看到补出来的默认值。
    """
    from core import copilot, resources

    table = resources.char_table() or {}
    by_stars = {}
    for c in table.values():
        if isinstance(c, dict) and c.get('name'):
            by_stars.setdefault(int(c.get('rarity') or 0) + 1, c['name'])

    def own(name, stars, elite, level, mastery=(0, 0, 0), main=7):
        return {'name': name, 'rarity': stars, 'elite': elite, 'level': level,
                'mainSkillLevel': main, 'masteryLevels': list(mastery), 'moduleLevels': {}}

    # 每个星级：默认要求 dict，以及「满足 / 差一点」的两个账号样本
    cases = [
        # stars  默认要求                          满足样本                    不满足样本
        (6, {'elite': 2, 'level': 60, 'skill_level': 9},
            (2, 60, (3, 3, 3)), (2, 60, (0, 0, 0))),      # 专精不够 → 拦下
        (5, {'elite': 1, 'level': 60, 'skill_level': 7},
            (1, 60, (0, 0, 0), 7), (1, 60, (0, 0, 0), 6)),  # 技能 6 级 → 拦下
        (4, {'elite': 1, 'level': 60, 'skill_level': 7},
            (1, 60, (0, 0, 0), 7), (0, 55, (0, 0, 0), 7)),
        (3, {'elite': 1, 'level': 55, 'skill_level': 7},
            (1, 55, (0, 0, 0), 7), (1, 54, (0, 0, 0), 7)),
        (2, {'elite': 0, 'level': 30},
            (0, 30, (0, 0, 0), 0), (0, 29, (0, 0, 0), 0)),
        (1, {'elite': 0, 'level': 30},
            (0, 30, (0, 0, 0), 0), (0, 1, (0, 0, 0), 0)),
    ]
    for stars, want, ok_args, bad_args in cases:
        name = by_stars.get(stars)
        assert name, '资源包里找不到 %d 星干员，无法构造样本' % stars
        op = {'name': name, 'skill': 1}          # v1 条目：没有 requirements
        req = copilot.effective_req(op, stars)
        for k, v in want.items():
            assert req.get(k) == v, '%d 星默认要求 %s 应为 %r，实际 %r' % (stars, k, v, req.get(k))
        assert req.get('implied') is True, '补出来的默认要求要带 implied 标记'
        assert 'requirements' not in op, 'effective_req 不能往原条目里塞字段'
        assert copilot.req_met(op, own(name, stars, *ok_args)), \
            '%s %r 应满足默认要求' % (name, ok_args)
        assert not copilot.req_met(op, own(name, stars, *bad_args)), \
            '%s %r 不该被当成可用（v1 作业不是无要求）' % (name, bad_args)

    # 专精检查认条目里的技能序号：skill=2 看第二技能的专精
    op6 = {'name': by_stars[6], 'skill': 2}
    assert not copilot.req_met(op6, own(by_stars[6], 6, 2, 60, mastery=(3, 0, 0))), \
        '二技能没专精不该放行'
    assert copilot.req_met(op6, own(by_stars[6], 6, 2, 60, mastery=(3, 3, 0)))

    # 写了练度的 v2 条目不受默认值影响
    op2 = {'name': by_stars[6], 'skill': 2, 'requirements': {'elite': 1, 'level': 1}}
    assert copilot.effective_req(op2, 6)['elite'] == 1, '明确写了要求的不能被默认覆盖'
    assert 'implied' not in copilot.effective_req(op2, 6)

    # 压级号 vs v1 作业：六星精一（无专精）+ 五星精零 → mode 应为 train，不再是 ready
    content = {'opers': [
        {'name': by_stars[6], 'skill': 2},
        {'name': by_stars[5], 'skill': 1},
    ], 'groups': []}
    owned_map = {
        copilot.norm(by_stars[6]): own(by_stars[6], 6, 1, 60),
        copilot.norm(by_stars[5]): own(by_stars[5], 5, 0, 40),
    }
    mode, missing, training, total, detail, _six = copilot.match_operation(content, owned_map)
    assert not missing, '两个干员都拥有，不该判缺人'
    assert mode == 'train', '压级号打 v1 作业应判需补练度，实际 %r' % mode
    assert training == [by_stars[6], by_stars[5]], training
    assert all(d['req'].get('implied') for d in detail), 'detail 里应带默认练度要求'

    # 满练号（精二60 + 专三 / 精一60 + 技能7）打同一份 v1 作业：应为 ready
    owned_map[copilot.norm(by_stars[6])] = own(by_stars[6], 6, 2, 60, mastery=(3, 3, 3))
    owned_map[copilot.norm(by_stars[5])] = own(by_stars[5], 5, 1, 60, main=7)
    mode, missing, training, total, detail, _six = copilot.match_operation(content, owned_map)
    assert mode == 'ready' and not training, '满练号打 v1 作业不该被误伤'

    # 详情弹窗用的 detail_opers：requirements 也要补上默认
    dop = copilot.detail_opers(content)
    assert dop[0]['requirements']['elite'] == 2 and dop[0]['requirements']['implied']
    assert dop[0]['requirements']['skill_level'] == 9, '六星默认要带专三要求'
    assert 'requirements' not in content['opers'][0], '展示副本不能污染原始 content'


# ---------------------------------------------------------------- B10 悖论模拟
def check_paradox_plan():
    """悖论清单：解锁条件只看对应干员的精英化/等级

    悖论关卡是官方固定阵容，所以「能打不能打」= 这个干员的 elite/level 够不够；
    导入过的要能记住，下次默认不再勾。
    """
    from core import paradox

    t = paradox.table()
    assert t.get('count', 0) > 200, '悖论清单条数异常：%r' % t.get('count')
    for cid, e in (t.get('chars') or {}).items():
        assert e.get('stage', '').startswith('mem_'), '%s 的关卡代号不像悖论：%r' % (cid, e.get('stage'))
        assert e.get('name'), '%s 没有干员名' % cid
        assert e.get('elite') in (0, 1, 2), '%s 解锁精英化异常：%r' % (cid, e.get('elite'))

    sample = [(c, e) for c, e in sorted((t.get('chars') or {}).items()) if e['elite'] == 2]
    (a_cid, a_e), (b_cid, b_e) = sample[0], sample[1]
    snap = {'chars': [
        {'charId': a_cid, 'name': a_e['name'], 'rarity': 6, 'profession': '近卫',
         'elite': 2, 'level': 90},                        # 达标
        {'charId': b_cid, 'name': b_e['name'], 'rarity': 6, 'profession': '近卫',
         'elite': 1, 'level': 70},                        # 精英化不够
    ]}
    p = paradox.plan(snap)
    st = p['stats']
    assert st['owned'] == 2, '只应看到两个干员，实际 %r' % st
    assert st['ready'] == 1 and st['locked'] == 1, '达成判定错：%r' % st
    assert st['todo'] == 1 and st['imported'] == 0

    # 已导入标记：plan 要能读回来，且不再算进 todo
    paradox.mark_imported(snap, [a_e['stage']])
    p2 = paradox.plan(snap)
    assert p2['stats']['imported'] == 1 and p2['stats']['todo'] == 0, p2['stats']
    hit = [i for i in p2['items'] if i['stage'] == a_e['stage']][0]
    assert hit['imported'] is True and hit['importedAt'], hit


def check_maa_paradox_name():
    """写 MAA 时 Name 用可读名字，FilePath 仍按关卡代号命名"""
    src = open(os.path.join(REPO, 'backend', 'core', 'maa.py'), encoding='utf-8').read()
    assert "'Name': it.get('name') or stage_code" in src, 'maa.py 的 Name 取值被改回去了'
    assert "fname = '%s_%s.json' % (_safe(stage_code), cid)" in src, '作业文件名应仍用关卡代号'


# ---------------------------------------------------------------- C. 启动冒烟
def _copy_project(tmp):
    ignore = shutil.ignore_patterns(
        '.git', '.venv', 'venv', 'build', 'dist', 'config', 'skland',
        '__pycache__', '*.pyc', 'release')
    shutil.copytree(REPO, tmp, ignore=ignore, dirs_exist_ok=True)


def _wait_banner(proc, timeout=25):
    """从子进程输出里解析『界面 http://127.0.0.1:PORT/』"""
    import threading
    import time
    lines, ports = [], []

    def pump():
        for raw in proc.stdout:
            lines.append(raw.rstrip('\n'))
            m = re.search(r'127\.0\.0\.1:(\d+)', raw)
            if m:
                ports.append(int(m.group(1)))

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ports or proc.poll() is not None:
            break
        time.sleep(0.2)
    return (ports[0] if ports else None), lines


def _get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def check_boot_smoke():
    tmp = tempfile.mkdtemp(prefix='maaprts-smoke-')
    try:
        _copy_project(tmp)
        before = set(os.listdir(tmp))
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        proc = subprocess.Popen(
            [sys.executable, '-u', 'backend/main.py', '--no-window'],
            cwd=tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace')
        try:
            port, lines = _wait_banner(proc)
            assert port, '启动未输出端口；输出：\n  ' + '\n  '.join(lines[-8:])
            base = 'http://127.0.0.1:%d' % port

            for path in PROBE_API:
                status, _body = _get(base + path)
                assert status == 200, '%s 状态码 %s' % (path, status)

            status, body = _get(base + '/api/bootstrap')
            envelope = json.loads(body.decode('utf-8'))
            assert envelope.get('ok'), 'bootstrap 返回失败：%s' % envelope.get('error')
            paths = (envelope.get('data') or {}).get('paths') or {}
            sk = (paths.get('skland') or '').rstrip('\\/')
            assert sk.endswith('config\\skland') or sk.endswith('config/skland'), \
                '账号数据路径不对：%s' % paths.get('skland')
            assert (paths.get('tokens') or '').endswith('tokens.json'), \
                'token 文件路径不对：%s' % paths.get('tokens')

            applog = os.path.join(tmp, 'debug', 'app.log')
            assert os.path.isfile(applog), '没有生成 debug/app.log'
            assert os.path.isfile(os.path.join(tmp, 'config', 'skland', 'tokens.json')), \
                '没有生成加密 tokens.json'
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

        # 运行前后对比：副本根目录只允许新增 config/ 与 debug/
        new = set(os.listdir(tmp)) - before
        assert new <= {'config', 'debug'}, '运行后根目录出现预期外的新增：%s' % sorted(new)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 入口
def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    print('MAA-PRTS 冒烟测试  %s' % REPO)
    print('-' * 60)
    r = Report()

    r.check('A1 .bat 编码（UTF-8 无 BOM + CRLF）', check_bat_encoding)
    r.check('A2 全部 .py 可编译', check_py_compile)

    tmp = tempfile.mkdtemp(prefix='maaprts-smoke-unit-')
    try:
        _patch_settings(tmp)
        r.check('B1 DPAPI 加解密往返', check_vault_roundtrip)
        r.check('B2 DPAPI 篡改必报错', check_vault_tamper)
        r.check('B3 tokens 多账号读写/去重/密文', lambda: check_tokens_multi_account(tmp))
        r.check('B4 旧 tokens.txt 自动迁移', lambda: check_tokens_migration(tmp))
        r.check('B5 坏密文自愈（.broken + 警告）', lambda: check_tokens_selfheal(tmp))
        r.check('B6 畸形旧 txt 留证并警告', lambda: check_tokens_bad_txt(tmp))
        r.check('B7 作业 json 修正后 MaaCore 可解析', check_copilot_normalize)
        r.check('B8 难度位标志（普通/突袭/通用）', check_copilot_difficulty)
        r.check('B9 突袭关拆普通/突袭两行', check_copilot_variants)
        r.check('B10 悖论清单与解锁推算', check_paradox_plan)
        r.check('B11 悖论写 MAA 的命名', check_maa_paradox_name)
        r.check('B12 v1 作业默认练度（压级号不再误推）', check_copilot_v1_default_req)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    r.check('C1 启动 + 只读接口 + 目录零污染', check_boot_smoke)

    print('-' * 60)
    if r.fails:
        print('结果：FAIL（%d 项未通过）' % r.fails)
        return 1
    print('结果：全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
