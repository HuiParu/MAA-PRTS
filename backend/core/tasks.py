# -*- coding: utf-8 -*-
"""后台任务：跑耗时操作（拉 token、写 MAA）并让前端轮询进度"""
from __future__ import annotations

import threading
import time
import traceback
import uuid

_tasks = {}
_lock = threading.Lock()
_keep = 40


def create(title: str, fn=None) -> str:
    tid = uuid.uuid4().hex[:12]
    with _lock:
        _tasks[tid] = {
            'id': tid, 'title': title, 'status': 'running',
            'logs': [], 'result': None, 'error': None,
            'startedAt': time.time(), 'endedAt': None,
        }
        # 清理旧任务
        if len(_tasks) > _keep:
            for k in sorted(_tasks, key=lambda x: _tasks[x]['startedAt'])[:len(_tasks) - _keep]:
                if _tasks[k]['status'] != 'running':
                    _tasks.pop(k, None)

    if fn is None:
        return tid

    def run():
        try:
            res = fn() if fn else None
            finish(tid, result=res)
        except Exception as e:
            finish(tid, error='%s: %s' % (type(e).__name__, e),
                   result={'traceback': traceback.format_exc()})

    threading.Thread(target=run, daemon=True, name='task-' + tid).start()
    return tid


def finish(tid, result=None, error=None):
    with _lock:
        t = _tasks.get(tid)
        if not t:
            return
        t['status'] = 'error' if error else 'done'
        t['result'] = result
        t['error'] = error
        t['endedAt'] = time.time()


def log(tid, line: str):
    with _lock:
        t = _tasks.get(tid)
        if t is not None:
            t['logs'].append(str(line).rstrip('\n'))
            if len(t['logs']) > 800:
                del t['logs'][:200]


def log_factory(tid):
    return lambda line: log(tid, line)


def get(tid, since=0):
    with _lock:
        t = _tasks.get(tid)
        if not t:
            return None
        out = dict(t)
        out['logs'] = t['logs'][since:]
        out['logCount'] = len(t['logs'])
        return out
