# -*- coding: utf-8 -*-
"""森空岛内置登录：独立小窗 + WebView2 网络事件嗅探 token。

思路抄自 MaaEnd 的 ZiplineImport：内嵌 WebView2 打开官方页面，旁路抄
网络数据而不碰凭据——那边抄的是响应体，这边抄的是发往
zonai.skland.com 的请求头里的 token（就是「怎么拿 token」教用户 F12
手抓的那个头）。抓到后先走一遍 grant 接口验证有效，再关窗回填表单。

登录窗不交给 pywebview 管：它运行时 create_window 的子窗口路径会把
构造 Invoke 到主窗口 UI 线程，pythonnet 下两边互等 GIL，整个进程假死
（实测过）。这里自己起一个 STA 线程直接摆 WinForms Form + WebView2，
和主窗口互不相干；UserDataFolder 也单独放一个目录，登录态跨会话保留
（登录过一次，下次打开直接是已登录状态，秒拿 token）。
"""
from __future__ import annotations

import os
import threading
import time

from . import skland

LOGIN_URL = 'https://www.skland.com/'
SNIFF_FILTER = 'https://*.skland.com/*'

# phase: idle → opening → waiting ⇄ verifying → done / failed / closed
_lock = threading.Lock()
_state = {'phase': 'idle', 'error': '', 'token': ''}
_win = [None]               # {'form': .NET Form, 'wv': .NET WebView2}
_closed = [False]           # 登录窗已关闭（用户手动关或抓完自动关）
_cand_lock = threading.Lock()
_candidates = []            # 抓到的候选 token，等 watch 线程逐个验证
_seen = set()

WATCH_TIMEOUT = 15 * 60     # 用户慢悠悠登录也够用，超时强制收摊


def status():
    with _lock:
        return _status_locked()


def _status_locked():
    """已持有 _lock 时用的读法（threading.Lock 不可重入，别在锁内调 status()）"""
    d = {'phase': _state['phase'], 'error': _state['error']}
    if _state['phase'] == 'done':
        d['token'] = _state['token']
    return d


def start():
    """打开登录小窗并开始嗅探；已经在跑就直接返回当前状态"""
    with _lock:
        if _state['phase'] in ('opening', 'waiting', 'verifying'):
            return _status_locked()
        _state.update(phase='opening', error='', token='')

    # 只在桌面窗口模式下有意义：pywebview 没起来就没有 WebView2 环境，
    # 而且负责加载 WebView2 DLL 的正是 pywebview 的 edgechromium 后端
    import webview
    if not getattr(webview, 'guilib', None) or not webview.windows:
        return _fail('当前不是桌面窗口模式，请手动粘贴 token')

    _closed[0] = False
    with _cand_lock:
        _candidates.clear()
        _seen.clear()
    try:
        from System.Threading import Thread, ThreadStart, ApartmentState
        t = Thread(ThreadStart(_thread_main))
        t.SetApartmentState(ApartmentState.STA)
        t.IsBackground = True
        t.Start()
    except Exception as e:
        return _fail('打不开登录窗口：%s' % e)
    threading.Thread(target=_watch, daemon=True, name='skland-login').start()
    return status()


def cancel():
    _close_window()
    with _lock:
        if _state['phase'] != 'done':
            _state.update(phase='idle', error='')
    return status()


# ---------------------------------------------------------------- 登录窗线程
def _thread_main():
    """登录小窗自己的 STA 线程：摆 Form + WebView2，泵消息直到关窗"""
    try:
        import System.Windows.Forms as WinForms
        from System import Uri
        from System.Drawing import Size
        from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties

        form = WinForms.Form()
        form.Text = '森空岛登录 · 登录成功自动抓取 token'
        form.ClientSize = Size(560, 1000)      # 高 DPI 屏上小了会显得挤，整体放大一档
        form.MinimumSize = Size(460, 660)
        form.StartPosition = WinForms.FormStartPosition.CenterScreen

        wv = WebView2()
        props = CoreWebView2CreationProperties()
        props.UserDataFolder = _user_data_folder()
        wv.CreationProperties = props
        wv.Dock = WinForms.DockStyle.Fill
        wv.Source = Uri(LOGIN_URL)
        form.Controls.Add(wv)

        wv.CoreWebView2InitializationCompleted += _on_ready
        wv.NavigationCompleted += _on_nav_done
        form.FormClosed += _on_form_closed
        _win[0] = {'form': form, 'wv': wv}
        WinForms.Application.Run(form)
    except Exception as e:
        _fail('登录窗口出错：%s' % e)
    finally:
        _win[0] = None
        _closed[0] = True
        with _lock:
            if _state['phase'] in ('opening', 'waiting', 'verifying'):
                _state['phase'] = 'closed'


def _on_ready(sender, args):
    """WebView2 初始化完成（UI 线程回调）：挂上请求嗅探"""
    try:
        if not args.IsSuccess:
            _fail('WebView2 没起来（装一下 Microsoft Edge WebView2 Runtime？）')
            _close_window()
            return
        cwv = sender.CoreWebView2
        from Microsoft.Web.WebView2.Core import CoreWebView2WebResourceContext
        cwv.AddWebResourceRequestedFilter(SNIFF_FILTER, CoreWebView2WebResourceContext.All)
        cwv.WebResourceRequested += _on_request
        sender.ZoomFactor = 1.25              # 页面内容跟着窗口一起放大
        with _lock:
            if _state['phase'] == 'opening':
                _state['phase'] = 'waiting'
    except Exception as e:
        _fail('订阅网络事件失败：%s' % e)
        _close_window()


def _on_nav_done(_sender, args):
    """首页打开失败（断网/DNS）时给个明确提示，别让用户干等"""
    try:
        if not args.IsSuccess:
            with _lock:
                if _state['phase'] in ('opening', 'waiting'):
                    _state['error'] = '页面没加载出来（网络问题？），检查后可在小窗里按 F5 刷新'
    except Exception:
        pass


def _on_form_closed(*_a):
    _closed[0] = True
    with _lock:
        if _state['phase'] in ('opening', 'waiting', 'verifying'):
            _state['phase'] = 'closed'


def _close_window():
    """从任意线程关掉登录窗（Close 必须在它自己的 UI 线程上执行）"""
    win = _win[0]
    if not win:
        return
    try:
        form = win['form']
        if form.IsHandleCreated and not form.IsDisposed:
            from System.Windows.Forms import MethodInvoker
            form.BeginInvoke(MethodInvoker(form.Close))
    except Exception:
        pass


def _on_request(_sender, args):
    """UI 线程回调，只做轻活：把 token 请求头抄进候选队列"""
    try:
        it = args.Request.Headers.Iterate()
        tok = None
        while it.MoveNext():
            h = it.Current
            if h.Key.lower() == 'token':
                tok = h.Value
                break
        if tok and len(tok) > 20:
            with _cand_lock:
                if tok not in _seen:
                    _seen.add(tok)
                    _candidates.append(tok)
    except Exception:
        pass


# ---------------------------------------------------------------- 验证
def _watch():
    """守着候选队列：来了就用 grant 接口验证，有效即关窗收工"""
    deadline = time.time() + WATCH_TIMEOUT
    while time.time() < deadline:
        cand = None
        with _cand_lock:
            if _candidates:
                cand = _candidates.pop(0)
        if cand is None:
            if _closed[0]:
                _set_phase('closed')
                return
            time.sleep(0.4)
            continue
        _set_phase('verifying')
        ok, err = _verify(cand)
        if ok:
            with _lock:
                _state.update(phase='done', token=cand, error='')
            _close_window()
            return
        # 多半是页面里残留的过期 token：丢掉继续等用户登录后的新请求
        _set_phase('waiting', err)
    _set_phase('failed', '等太久了先收摊，也可以直接手动粘贴 token')
    _close_window()


def _verify(token):
    """候选 token 先用 grant 接口验一遍，别把过期值回填给用户"""
    try:
        g = skland._http(
            'POST', skland.GRANT_URL,
            {'User-Agent': skland.SKLAND_UA, 'Accept-Encoding': 'identity',
             'Connection': 'close', 'dId': skland.DID},
            {'appCode': skland.APP_CODE, 'token': token, 'type': 0},
            timeout=12, retries=1)
        if g.get('status') == 0:
            return True, ''
        return False, 'token 换 grant 失败：%s' % (g.get('msg') or g)
    except Exception as e:
        return False, '验证请求失败：%s' % e


# ---------------------------------------------------------------- 内部工具
def _fail(msg):
    with _lock:
        _state.update(phase='failed', error=msg)
    return status()


def _set_phase(phase, error=''):
    with _lock:
        _state.update(phase=phase, error=error)


def _user_data_folder():
    """登录窗专属 UDF（和主窗口的分开，避免 WebView2 environment 冲突）"""
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = os.path.join(base, 'pywebview', 'skland-login')
    os.makedirs(d, exist_ok=True)
    return d
