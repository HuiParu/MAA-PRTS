# -*- coding: utf-8 -*-
"""账号配置：读取 accounts/*.json、内置 token 同步"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import threading

from . import settings, tasks, updater

ELITE_CN = {0: '精零', 1: '精一', 2: '精二'}


def _accounts_dir():
    return settings.accounts_dir()


def _load(path):
    try:
        with io.open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def list_accounts():
    out = []
    d = _accounts_dir()
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith('.json') or name.startswith(('_', '作业站')):
            continue
        snap = _load(os.path.join(d, name))
        if not snap or not (snap.get('account') or {}).get('uid'):
            continue
        a, s = snap.get('account') or {}, snap.get('stats') or {}
        out.append({
            'file': name,
            'uid': str(a.get('uid')),
            'nickName': a.get('nickName') or name,
            'alias': a.get('alias') or '',
            'channelName': a.get('channelName') or '',
            'level': a.get('level'),
            'secretary': a.get('secretary') or {},
            'maaProfile': (snap.get('maa') or {}).get('profile') or '',
            'syncedAt': (snap.get('sync') or {}).get('syncedAt'),
            'stats': {
                'charCount': s.get('charCount'),
                'charTotal': s.get('charTotal'),
                'missingCount': s.get('missingCount'),
                'sixStarCount': s.get('sixStarCount'),
                'sixStarTotal': s.get('sixStarTotal'),
                'e2Count': s.get('e2Count'),
                'mastery3Count': s.get('mastery3Count'),
                'moduleCount': s.get('moduleCount'),
                'byRarity': s.get('byRarity') or {},
            },
        })
    out.sort(key=lambda r: (-(r['stats']['charCount'] or 0), r['nickName']))
    return out


def get_account(file: str) -> dict:
    path = os.path.join(_accounts_dir(), os.path.basename(file))
    snap = _load(path)
    if not snap:
        raise FileNotFoundError('账号文件不存在：%s' % file)
    return snap


def account_detail(file: str) -> dict:
    snap = get_account(file)
    a, s = snap.get('account') or {}, snap.get('stats') or {}
    chars = []
    for c in snap.get('chars') or []:
        chars.append({
            'charId': c.get('charId'),
            'name': c.get('name'),
            'rarity': c.get('rarity'),
            'profession': c.get('profession'),
            'subProfession': c.get('subProfession'),
            'elite': c.get('elite'),
            'level': c.get('level'),
            'potential': c.get('potential'),
            'skillLevel': c.get('skillLevel'),
            'mastery': max([int(x.get('mastery') or 0) for x in (c.get('skills') or [])] or [0]),
            'modules': len(c.get('modules') or []),
            'favor': c.get('favor'),
        })
    chars.sort(key=lambda r: (-(r['rarity'] or 0), -(r['elite'] or 0), -(r['level'] or 0), r['name'] or ''))
    return {
        'file': file,
        'account': a,
        'stats': s,
        'missing': snap.get('missing') or [],
        'chars': chars,
        'maa': snap.get('maa') or {},
        'sync': snap.get('sync') or {},
    }


def save_maa_meta(file: str, patch: dict) -> dict:
    """把 MAA 配置名等用户字段写回账号 json"""
    path = os.path.join(_accounts_dir(), os.path.basename(file))
    snap = _load(path)
    if not snap:
        raise FileNotFoundError(file)
    maa = snap.setdefault('maa', {})
    for k, v in (patch or {}).items():
        maa[k] = v
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return maa


# ---------------------------------------------------------------- token 存储
# config/skland/tokens.json：多账号列表，逐条经 Windows DPAPI（CurrentUser）
# 加密后存放，密钥绑定本机 + 当前 Windows 用户，拷到别的电脑无法解密。
# 文件格式与迁移说明见 config/skland/README.md。

from . import vault  # noqa: E402


def _migrate_txt_if_any():
    """旧版明文 tokens.txt → 加密 tokens.json

    先写 tokens.json 成功、再把原 txt 改名 .bak——中途任何一步失败，
    原数据都还在；txt 读不了（编码坏等）则改名 .broken 留证并报错。
    """
    txt = os.path.join(settings.skland_dir(), 'tokens.txt')
    path = settings.tokens_file()
    if not os.path.isfile(txt) or os.path.isfile(path):
        return
    try:
        items = [{'alias': alias or '', 'token': token}
                 for alias, token, _out, _line in updater.parse_tokens_file(txt)
                 if token]
    except Exception:
        os.replace(txt, txt + '.broken')
        raise ValueError('旧 tokens.txt 读取失败（编码损坏？），已改名为 %s，'
                         '请手动检查。' % os.path.basename(txt + '.broken'))
    _save_tokens(items)
    os.replace(txt, txt + '.bak')


def _save_tokens(items: list):
    """逐条加密落盘：文件里能看到有几条、备注是什么，token 本身是密文"""
    path = settings.tokens_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    env = {
        'version': 2,
        'cipher': 'dpapi',
        'note': 'Windows DPAPI(CurrentUser) 逐条加密：仅本机当前 Windows 用户可解，拷到别的电脑无效。',
        'tokens': [
            {
                'alias': (e.get('alias') or '').strip(),
                'addedAt': e.get('addedAt') or '',
                'data': base64.b64encode(
                    vault.protect((e.get('token') or '').strip().encode('utf-8'))
                ).decode('ascii'),
            }
            for e in items if (e.get('token') or '').strip()
        ],
    }
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(env, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def load_tokens() -> list:
    """读出 token 条目 [{"alias", "token", "addedAt"}]；解不开时给出明确报错"""
    path = settings.tokens_file()
    _migrate_txt_if_any()
    if not os.path.isfile(path):
        return []
    env = _load(path) or {}
    if env.get('cipher') != 'dpapi' or not isinstance(env.get('tokens'), list):
        raise ValueError('%s 不是有效的加密 token 文件' % os.path.basename(path))
    items = []
    for i, ent in enumerate(env['tokens'], 1):
        try:
            token = vault.unprotect(base64.b64decode(ent.get('data') or '')).decode('utf-8')
        except Exception:
            raise ValueError(
                'tokens.json 第 %d 条无法解密：密钥绑定本机与当前 Windows 用户，'
                '换电脑 / 换用户后需要重新粘贴 token。' % i)
        if token.strip():
            items.append({'alias': (ent.get('alias') or '').strip(),
                          'token': token.strip(),
                          'addedAt': ent.get('addedAt') or ''})
    return items


# 启动自检发现 token 文件读不开时，把原因存这里，main 起来后写进 app.log
TOKENS_WARNING = ''


def ensure_tokens() -> list:
    """启动自检：迁移旧 txt → 读加密文件；读不开就把坏文件改名留证、重建空的"""
    global TOKENS_WARNING
    TOKENS_WARNING = ''
    try:
        items = load_tokens()
    except ValueError as e:
        broken = settings.tokens_file() + '.broken'
        try:
            os.replace(settings.tokens_file(), broken)
        except Exception:
            pass
        _save_tokens([])
        items = []
        TOKENS_WARNING = ('%s；已把原文件改名为 %s，请在界面里重新添加账号。'
                          % (e, os.path.basename(broken)))
    if not os.path.isfile(settings.tokens_file()):
        _save_tokens([])
    return items


def remember_token(token: str, alias: str = '') -> bool:
    """把界面上粘贴的 token 记入加密存储，返回是否新增"""
    token = (token or '').strip()
    if not token:
        return False
    items = load_tokens()
    if any(e.get('token') == token for e in items):
        return False
    items.append({'alias': (alias or '').strip(), 'token': token,
                  'addedAt': updater.now_iso()})
    _save_tokens(items)
    return True


# ---------------------------------------------------------------- 刷新
def _run_updater(tid, token=None, alias=None, with_skins=False):
    """内置同步（不依赖外部 python 脚本，可直接打包进 exe）"""
    log = tasks.log_factory(tid)

    if token:
        if remember_token(token, alias or ''):
            log('已把 token 记到 %s' % settings.tokens_file())

    # 让 skland 把重试提示也打到界面日志里
    updater.skland.set_logger(log)

    if token:
        return updater.sync_one(token, alias or '', settings.accounts_dir(),
                                log, with_skins=with_skins,
                                cache_path=settings.subprof_cache())
    return updater.sync_many(load_tokens(), settings.accounts_dir(),
                             log, with_skins=with_skins,
                             cache_path=settings.subprof_cache())


def start_refresh(token=None, alias=None, with_skins=False, title=None):
    """启动后台同步，返回任务 id（前端轮询 /api/task）"""
    title = title or ('同步账号 ' + (token[:6] + '…' if token else '（全部）'))
    holder = {}

    def go():
        try:
            res = _run_updater(holder['tid'], token, alias, with_skins)
            rows = list_accounts()
            if isinstance(res, dict) and res.get('fail'):
                tasks.finish(holder['tid'], result={'accountCount': len(rows)},
                             error='%d 个 token 同步失败（看日志）' % res['fail'])
                return
            newest = None
            if token and isinstance(res, dict) and res.get('files'):
                newest = res['files'][0]['file']
            elif rows:
                newest = max(rows, key=lambda r: r.get('syncedAt') or '')['file']
            tasks.finish(holder['tid'], result={'accountCount': len(rows), 'newest': newest})
        except Exception as e:
            import traceback
            tasks.finish(holder['tid'], error='%s: %s' % (type(e).__name__, e),
                         result={'traceback': traceback.format_exc()})

    tid = tasks.create(title, None)
    holder['tid'] = tid
    threading.Thread(target=go, daemon=True, name='sync').start()
    return tid


def remove_account(file: str, backup=True):
    path = os.path.join(_accounts_dir(), os.path.basename(file))
    if not os.path.isfile(path):
        raise FileNotFoundError(file)
    if backup:
        bak_dir = os.path.join(os.path.dirname(path), '_removed')
        os.makedirs(bak_dir, exist_ok=True)
        shutil.move(path, os.path.join(bak_dir, os.path.basename(path)))
    else:
        os.remove(path)
    return True
