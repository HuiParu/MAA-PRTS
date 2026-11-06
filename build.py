# -*- coding: utf-8 -*-
"""打包脚本：生成图标 + 调 PyInstaller 出 exe

用法：python build.py
入口：backend/main.py
产物：build/MAA-PRTS/MAA-PRTS.exe（整个文件夹即发布包，拷走即用）
构建只写 build/ 一个目录；中间产物放 build/work/，成功后自动删掉。

打包只带只读资源（frontend / resources）。用户数据永远写在 exe 同目录的
config/（含加密 token 与账号练度），不会被打进包里；程序任何模式下都不向上
找目录。压缩发版请用全新构建产物（运行过会多出 config/、debug/）。
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
    # 构建只写 build/ 一个目录：work/ 是中间产物，MAA-PRTS/ 是发布包本体。
    # 每次全清这两个子目录（build/ 本身无入库文件，全部是产物）。
    build_dir = os.path.join(HERE, 'build')
    work_dir = os.path.join(build_dir, 'work')
    for d in (work_dir, os.path.join(build_dir, 'MAA-PRTS')):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm', '--clean',
        '--name', 'MAA-PRTS',
        '--distpath', build_dir,
        '--workpath', work_dir,
        '--specpath', work_dir,
        '--windowed',
        # 指定了 specpath 后，--add-data 的源路径必须用绝对路径
        '--add-data', os.path.join(HERE, 'frontend') + ';frontend',
        '--add-data', os.path.join(HERE, 'resources') + ';resources',
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
        print('\n打包失败，退出码 %d（中间产物保留在 build\\work 以便排查）' % rc)
        return rc

    # 每次构建都是 --clean 全量重建，中间产物没有复用价值，成功即删
    shutil.rmtree(work_dir, ignore_errors=True)

    exe = os.path.join(build_dir, 'MAA-PRTS', 'MAA-PRTS.exe')
    print('\n完成：%s' % exe)
    if os.path.isfile(exe):
        size = os.path.getsize(exe) / 1024 / 1024
        print('  主程序 %.1f MB' % size)
    return 0


if __name__ == '__main__':
    sys.exit(build())
