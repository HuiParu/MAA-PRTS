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
