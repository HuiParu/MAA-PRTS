# -*- coding: utf-8 -*-
"""MAA-PRTS 作业控制台 · 启动器

pywebview（WebView2）原生窗口 + 内置 HTTP 服务。
打包后是单文件夹 exe，不依赖外部 python。
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import accounts, api, settings, version  # noqa: E402

WEB = settings.static_dir()
LOG_PATH = settings.LOG_PATH
_last_ping = [time.time()]
_started = [time.time()]
_srv = [None]


# ---------------------------------------------------------------- 日志
def log(msg):
    line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
    try:
        if sys.stdout:
            print(line, flush=True)
    except Exception:
        pass
    try:
        os.makedirs(settings.CONFIG_DIR, exist_ok=True)
        if os.path.isfile(LOG_PATH) and os.path.getsize(LOG_PATH) > 2 * 1024 * 1024:
            os.replace(LOG_PATH, LOG_PATH + '.1')
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = 'MAA-PRTS/%s' % version.APP_VERSION
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body: bytes, ctype='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def _err(self, msg, code=400):
        self._json({'ok': False, 'error': str(msg)}, code)

    def _query(self):
        p = urllib.parse.urlparse(self.path)
        return {k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()}, p.path

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode('utf-8'))
        except Exception:
            return {}

    def _static(self, path):
        if path in ('/', ''):
            path = '/index.html'
        rel = path.lstrip('/')
        if rel.startswith('static/'):
            rel = rel[len('static/'):]
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(os.path.normpath(WEB)) or not os.path.isfile(full):
            self._send(404, b'not found', 'text/plain; charset=utf-8')
            return
        ext = os.path.splitext(full)[1].lower()
        with open(full, 'rb') as f:
            data = f.read()
        self._send(200, data, api.MIME.get(ext, 'application/octet-stream'))

    def do_GET(self):
        q, path = self._query()
        if path.startswith('/api/'):
            if path == '/api/ping':
                _last_ping[0] = time.time()
                self._json({'ok': True})
                return
            fn = api.ROUTES.get(path)
            if not fn:
                self._err('接口不存在：' + path, 404)
                return
            try:
                self._json({'ok': True, 'data': fn(q, {})})
            except Exception as e:
                self._fail(e)
            return
        self._static(path)

    def do_POST(self):
        q, path = self._query()
        if path == '/api/ping':
            _last_ping[0] = time.time()
            self._json({'ok': True})
            return
        fn = api.ROUTES.get(path)
        if not fn:
            self._err('接口不存在：' + path, 404)
            return
        try:
            self._json({'ok': True, 'data': fn(q, self._body())})
        except Exception as e:
            self._fail(e)

    def _fail(self, e):
        tb = traceback.format_exc()
        log(tb)
        self._json({'ok': False, 'error': '%s: %s' % (type(e).__name__, e),
                    'trace': tb.splitlines()[-3:]}, 500)


def find_port(start=8787, tries=40):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Windows 上 SO_REUSEADDR 会允许两个进程绑同一端口（互相抢连接），
            # 必须用独占绑定，第二个实例才会自动顺延到下一个端口。
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                except OSError:
                    pass
            else:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    raise RuntimeError('找不到可用端口')


# ---------------------------------------------------------------- 前端可调用的原生能力
class Bridge:
    """暴露给 JS：window.pywebview.api.xxx()"""

    def app_info(self):
        return {
            'version': version.APP_VERSION,
            'gamedata': version.pack_meta()['version'],
            'frozen': settings.FROZEN,
            'root': settings.project_root(),
            'sklandDir': settings.skland_dir(),
            'configDir': settings.CONFIG_DIR,
            'webDir': WEB,
            'logPath': LOG_PATH,
            'native': True,
        }

    def open_folder(self, which='skland'):
        """打开项目内的数据目录（skland / config / accounts）"""
        table = {
            'skland': settings.skland_dir(),
            'accounts': settings.accounts_dir(),
            'config': settings.CONFIG_DIR,
            'root': settings.project_root(),
        }
        path = table.get(str(which or 'skland').lower()) or settings.skland_dir()
        os.makedirs(path, exist_ok=True)
        return self.open_path(path)

    def choose_folder(self, title='选择文件夹', initial=''):
        import webview
        try:
            res = webview.windows[0].create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=initial or '',
                allow_multiple=False,
            )
            if not res:
                return {'path': None}
            if isinstance(res, (list, tuple)):
                return {'path': res[0] if res else None}
            return {'path': res}
        except Exception as e:
            return {'path': None, 'error': str(e)}

    def open_path(self, path):
        """用系统默认方式打开文件/文件夹"""
        try:
            if not path or not os.path.exists(path):
                return {'ok': False, 'error': '路径不存在：%s' % path}
            os.startfile(path)  # noqa: S606 (Windows only)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def open_url(self, url):
        try:
            webbrowser.open(url)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def quit(self):
        os._exit(0)

    def minimize(self):
        return {'ok': True}


def serve(port):
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    srv.daemon_threads = True
    _srv[0] = srv
    srv.serve_forever()


def main():
    no_window = '--no-window' in sys.argv
    debug = '--debug' in sys.argv
    port = find_port()
    threading.Thread(target=serve, args=(port,), daemon=True, name='http').start()
    url = 'http://127.0.0.1:%d/' % port
    time.sleep(0.25)

    st = settings.load()
    accounts.ensure_tokens_file()
    log('=' * 56)
    log('MAA-PRTS %s  界面 %s' % (version.APP_VERSION, url))
    log('项目目录  %s' % settings.project_root())
    log('账号数据  %s' % settings.skland_dir())
    log('配置文件  %s' % settings.SETTINGS_PATH)
    log('MAA 目录  %s' % (st['maaDir'] or '（尚未设置，首次启动会提示）'))
    log('=' * 56)

    if no_window:
        log('（--no-window：只起服务，用浏览器打开上面的地址）')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return 0

    import webview
    webview.create_window(
        'MAA-PRTS · 作业控制台',
        url,
        width=1520,
        height=960,
        min_size=(1120, 720),
        background_color='#0b0e14',
        easy_drag=False,
        js_api=Bridge(),
    )
    webview.start(debug=debug, private_mode=False)
    log('窗口已关闭，退出')
    try:
        if _srv[0]:
            _srv[0].shutdown()
    except Exception:
        pass
    os._exit(0)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        log(traceback.format_exc())
        raise
