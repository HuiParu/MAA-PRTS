# -*- coding: utf-8 -*-
"""账号配置：读取 accounts/*.json、内置 token 同步"""
from __future__ import annotations

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
TOKENS_HEADER = """# ============================================================
# 森空岛 token 列表（一行一个账号，文件在项目 skland/ 目录内）
# 写法：
#   token                      只有 token
#   备注:token                  带备注（备注只用于日志和 alias 字段）
#   备注:token:文件名.json      指定生成的账号文件名
# 以 # 开头的是注释；同一 token 写多次只处理第一次。
# 界面里「添加账号」也会自动追加到这里，方便以后一键同步全部。
# ============================================================
"""


def ensure_tokens_file() -> str:
    """tokens.txt 不存在就建一个只带注释的模板"""
    path = settings.tokens_file()
    if not os.path.isfile(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(TOKENS_HEADER)
    return path


def _token_exists(path: str, token: str) -> bool:
    try:
        with io.open(path, encoding='utf-8-sig') as f:
            for raw in f:
                s = raw.strip()
                if not s or s.startswith('#'):
                    continue
                if s.split(':')[-1].strip() == token or s == token:
                    return True
    except Exception:
        pass
    return False


def remember_token(token: str, alias: str = '') -> bool:
    """把界面上粘贴的 token 记到 skland/tokens.txt，返回是否新增"""
    token = (token or '').strip()
    if not token:
        return False
    path = ensure_tokens_file()
    if _token_exists(path, token):
        return False
    line = ('%s:%s' % (alias.strip(), token)) if alias and alias.strip() else token
    with io.open(path, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
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
    return updater.sync_many(ensure_tokens_file(), settings.accounts_dir(),
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
