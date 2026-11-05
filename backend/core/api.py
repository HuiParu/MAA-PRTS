# -*- coding: utf-8 -*-
"""HTTP API：给前端页面用的 JSON 接口"""
from __future__ import annotations

import json
import os
import traceback
import urllib.parse

from . import accounts, copilot, maa, paradox, resources, settings, tasks, version

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = settings.static_dir()

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
    '.woff2': 'font/woff2',
}


def _account_for(file):
    if not file:
        last = settings.load().get('lastAccount')
        rows = accounts.list_accounts()
        if last and any(r['file'] == last for r in rows):
            return last
        if rows:
            return rows[0]['file']
        raise RuntimeError('还没有账号，先用森空岛 token 添加一个')
    return file


# ---------------------------------------------------------------- 路由
def bootstrap(_q, _body):
    st = settings.load()
    accs = accounts.list_accounts()
    status = maa.status()
    acts = resources.activity_list(18)
    return {
        'settings': {k: st[k] for k in ('maaDir', 'profile', 'autoStartMaa')},
        'accounts': accs,
        'lastAccount': _account_for_last(st, accs),
        'maa': status,
        'activities': acts,
        'paths': {
            'root': settings.project_root(),
            'skland': settings.skland_dir(),
            'accounts': settings.accounts_dir(),
            'tokens': settings.tokens_file(),
            'config': settings.CONFIG_DIR,
        },
        'pack': resources.pack_info(),
        'gamedata': version.check(acts),
        'setup': {
            # 首次启动引导：没账号 = 还没填 token；MAA 路径无效 = 还没填根目录
            'needsToken': not accs,
            'needsMaa': not status.get('exeExists'),
        },
        'version': version.APP_VERSION,
    }


def _account_for_last(st, accs):
    last = st.get('lastAccount')
    if last and any(a['file'] == last for a in accs):
        return last
    return accs[0]['file'] if accs else ''


def api_settings(_q, body):
    patch = body or {}
    st = settings.save(patch)
    status = maa.status()
    return {'settings': st, 'maa': status}


def api_accounts(_q, _body):
    return {'accounts': accounts.list_accounts()}


def api_account(q, _body):
    file = _account_for(q.get('file'))
    return accounts.account_detail(file)


def api_account_maa(_q, body):
    body = body or {}
    return {'maa': accounts.save_maa_meta(body['file'], body.get('patch') or {})}


def api_account_remove(_q, body):
    return {'removed': accounts.remove_account((body or {}).get('file'))}


def api_refresh(_q, body):
    body = body or {}
    token = (body.get('token') or '').strip() or None
    tid = accounts.start_refresh(token=token, alias=(body.get('alias') or '').strip() or None,
                                 with_skins=bool(body.get('withSkins')))
    return {'taskId': tid}


def api_search(_q, body):
    body = body or {}
    kw = (body.get('q') or '').strip()
    if not kw:
        raise ValueError('请输入关卡代号（如 TL-10）、活动（act55side / 残照终尽）或关卡系列（TR-）')
    file = _account_for(body.get('file'))
    snap = accounts.get_account(file)
    res = copilot.search(kw, snap, pages=int(body.get('pages') or 2),
                         min_rating=int(body.get('minRating') or 0),
                         limit=int(body.get('limit') or 12))
    res['file'] = file
    return res


def api_activities(_q, _body):
    return {'activities': resources.activity_list(24)}


def api_gamedata(_q, _body):
    """资源包版本状态（含是否有待提示的更新）"""
    return version.check(resources.activity_list(18))


def api_gamedata_ack(_q, _body):
    """用户点「知道了」之后清掉更新提示"""
    return version.ack(resources.activity_list(18))


def api_op(q, _body):
    cid = q.get('id')
    if not cid:
        raise ValueError('缺少作业 id')
    d = copilot.operation_detail(cid)
    content = d['content']
    return {
        'id': int(cid),
        'content': content,
        'maaCode': 'maa://%s' % cid,
        'title': (content.get('doc') or {}).get('title'),
        'opers': copilot.detail_opers(content),
        'actions': len(content.get('actions') or []),
        'stageName': content.get('stage_name'),
    }


def api_maa_status(_q, _body):
    return maa.status()


def api_maa_probe(q, _body):
    """检测一个目录是不是 MAA 根目录（首次引导 / 设置里用）"""
    d = (q.get('dir') or '').strip()
    if not d:
        raise ValueError('缺少目录参数')
    exe = os.path.join(d, 'MAA.exe')
    cfg_path = os.path.join(d, 'config', 'gui.new.json')
    profiles = []
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding='utf-8') as f:
                cfg = json.load(f)
            profiles = list((cfg.get('Configurations') or {}).keys())
        except Exception:
            pass
    return {
        'dir': d,
        'exeExists': os.path.isfile(exe),
        'configExists': os.path.isfile(cfg_path),
        'profiles': profiles,
    }


def api_maa_close(_q, _body):
    return {'closed': maa.close(), 'running': maa.is_running()}


def api_maa_open(_q, _body):
    return {'started': maa.launch()}


def api_maa_apply(_q, body):
    body = body or {}
    items = body.get('items') or []
    if not items:
        raise ValueError('作业集是空的')
    tid = maa.start_apply(items, profile=body.get('profile'),
                          mode=body.get('mode') or 'replace',
                          auto_start=body.get('autoStart', True))
    return {'taskId': tid}


def api_maa_clear(_q, body):
    return {'cleared': maa.clear_tasklist((body or {}).get('profile'))}


def api_maa_tasklist(q, _body):
    return maa.tasklist(q.get('profile'))


def api_paradox_plan(q, body):
    """当前账号的悖论模拟清单（练度推算，不打任何图片主意）"""
    body = body or {}
    file = _account_for(q.get('file') or body.get('file'))
    snap = accounts.get_account(file)
    out = paradox.plan(snap)
    out['file'] = file
    return out


def api_paradox_pick(_q, body):
    """按选中的关卡号批量取作业（每关一份最优）"""
    body = body or {}
    file = _account_for(body.get('file'))
    stages = body.get('stages') or []
    if not stages:
        raise ValueError('没有选中任何悖论关卡')
    snap = accounts.get_account(file)
    res = paradox.pick(stages, snap)
    res['file'] = file
    return res


def api_paradox_mark(_q, body):
    """记下这些悖论已经排进过 MAA，下次默认不勾"""
    body = body or {}
    file = _account_for(body.get('file'))
    snap = accounts.get_account(file)
    imp = paradox.mark_imported(snap, body.get('stages') or [])
    accounts.save_account(file, snap)
    return {'file': file, 'imported': len(imp)}


def api_task(q, _body):
    tid = q.get('id')
    t = tasks.get(tid, int(q.get('since') or 0))
    if not t:
        raise FileNotFoundError('任务不存在或已过期')
    return t


def api_export(_q, body):
    """导出作业站「本地导入」用的干员 JSON"""
    body = body or {}
    file = _account_for(body.get('file'))
    snap = accounts.get_account(file)
    data = []
    for c in snap.get('chars') or []:
        if not c.get('charId') or not c.get('level'):
            continue
        equips = []
        for m in c.get('modules') or []:
            t = copilot._module_type(m.get('id'))
            if t:
                equips.append({'type': t, 'level': int(m.get('level') or 0)})
        data.append({
            'id': c['charId'], 'name': c.get('name'), 'rarity': int(c.get('rarity') or 0),
            'evolvePhase': int(c.get('elite') or 0), 'level': int(c.get('level') or 0),
            'mainSkillLevel': int(c.get('skillLevel') or 0),
            'skills': [{'level': int(s.get('mastery') or 0)} for s in (c.get('skills') or [])],
            'equips': equips,
        })
    out_dir = os.path.join(settings.accounts_dir(), '作业站')
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(file)[0]
    path = os.path.join(out_dir, '作业站干员_%s.json' % stem)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'code': 200, 'message': 'ok', 'data': data}, f, ensure_ascii=False, indent=2)
    return {'path': path, 'count': len(data)}


ROUTES = {
    '/api/bootstrap': bootstrap,
    '/api/settings': api_settings,
    '/api/accounts': api_accounts,
    '/api/account': api_account,
    '/api/account/maa': api_account_maa,
    '/api/account/remove': api_account_remove,
    '/api/account/refresh': api_refresh,
    '/api/search': api_search,
    '/api/activities': api_activities,
    '/api/gamedata': api_gamedata,
    '/api/gamedata/ack': api_gamedata_ack,
    '/api/op': api_op,
    '/api/maa/status': api_maa_status,
    '/api/maa/probe': api_maa_probe,
    '/api/maa/close': api_maa_close,
    '/api/maa/open': api_maa_open,
    '/api/maa/apply': api_maa_apply,
    '/api/maa/clear': api_maa_clear,
    '/api/maa/tasklist': api_maa_tasklist,
    '/api/task': api_task,
    '/api/export': api_export,
    '/api/paradox/plan': api_paradox_plan,
    '/api/paradox/pick': api_paradox_pick,
    '/api/paradox/mark': api_paradox_mark,
}
