# -*- coding: utf-8 -*-
"""打包脚本：生成图标 + 调 PyInstaller 出 exe

用法：python build.py
入口：backend/main.py
产物：dist/MAA-PRTS/MAA-PRTS.exe（单文件夹，双击即用）

打包只带只读资源（frontend / resources）。用户数据（skland / config）
永远写在 exe 所在项目根目录，不会被打进包里。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, 'resources', 'assets', 'app.ico')


def make_icon():
    """用 Pillow 画一个图标：深色圆角方块 + 薄荷色六边形 + 播放三角"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print('未安装 Pillow，跳过图标生成（用系统默认图标）')
        return None

    os.makedirs(os.path.dirname(ICON), exist_ok=True)
    S = 1024
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 背景：圆角方块 + 竖向渐变
    r = int(S * 0.22)
    bg = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    for y in range(S):
        t = y / S
        col = (
            int(18 + 10 * t),
            int(23 + 14 * t),
            int(34 + 20 * t),
            255,
        )
        bd.line([(0, y), (S, y)], fill=col)
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=255)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # 外环六边形
    cx, cy, R = S // 2, int(S * 0.5), int(S * 0.33)
    hex_pts = []
    for i in range(6):
        import math
        a = math.radians(60 * i - 90)
        hex_pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))
    d.line(hex_pts + [hex_pts[0]], fill=(97, 227, 208, 235), width=int(S * 0.028), joint='curve')

    # 六边形内的小六边形（描边）
    R2 = int(R * 0.62)
    hex2 = []
    for i in range(6):
        import math
        a = math.radians(60 * i - 90)
        hex2.append((cx + R2 * math.cos(a), cy + R2 * math.sin(a)))
    d.line(hex2 + [hex2[0]], fill=(97, 227, 208, 110), width=int(S * 0.016), joint='curve')

    # 中央播放三角
    tR = int(S * 0.115)
    d.polygon([(cx - tR * 0.72, cy - tR), (cx - tR * 0.72, cy + tR), (cx + tR, cy)],
              fill=(120, 240, 220, 255))

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ICON, format='ICO', sizes=sizes)
    print('图标已生成：%s' % ICON)
    return ICON


def build():
    icon = make_icon()
    # 只清打包产物，保留 dist/README.md 与用户放在 dist 里的东西
    for d in ('build', os.path.join('dist', 'MAA-PRTS')):
        p = os.path.join(HERE, d)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm', '--clean',
        '--name', 'MAA-PRTS',
        '--windowed',
        '--add-data', 'frontend;frontend',
        '--add-data', 'resources;resources',
        '--hidden-import', 'clr',
        '--hidden-import', 'clr_loader',
        '--hidden-import', 'pythonnet',
        '--collect-submodules', 'webview',
        '--paths', os.path.join(HERE, 'backend'),
        os.path.join('backend', 'main.py'),
    ]
    if icon and os.path.isfile(icon):
        cmd[cmd.index('--windowed') + 1:cmd.index('--windowed') + 1] = ['--icon', icon]

    print('执行：\n  ' + ' '.join(cmd))
    rc = subprocess.call(cmd, cwd=HERE)
    if rc != 0:
        print('\n打包失败，退出码 %d' % rc)
        return rc

    exe = os.path.join(HERE, 'dist', 'MAA-PRTS', 'MAA-PRTS.exe')
    print('\n完成：%s' % exe)
    if os.path.isfile(exe):
        size = os.path.getsize(exe) / 1024 / 1024
        print('  主程序 %.1f MB' % size)
    return 0


if __name__ == '__main__':
    sys.exit(build())
