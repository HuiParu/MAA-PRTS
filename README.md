# MAA-PRTS · 明日方舟作业控制台

用森空岛 token 读取账号练度，自动比对 [prts.plus](https://prts.plus/) 作业站的干员要求，
告诉你哪份作业能直接抄、哪份差一个人、哪份练度不够；挑好后一键写进 MAA 的多作业列表。

整个程序**不依赖外部脚本和游戏资源目录**，token、账号配置、日志全部保存在本项目的
`skland/` 与 `config/` 里，随时可以整个文件夹打包带走。

## 下载

**[⬇ MAA-PRTS v2.2.0 · Windows x64（12.5 MB）](https://github.com/HuiParu/MAA-PRTS/releases/latest)**

解压到任意可写目录（不要放 `C:\Program Files`），双击 `MAA-PRTS.exe` 即可。
`_internal` 文件夹必须和 exe 放在一起，别只把 exe 拖出来。

```
MAA-PRTS\
  MAA-PRTS.exe
  _internal\        ← 必须一起保留
  README.txt        ← token 获取步骤 + 常见问题
```

首次启动会引导两步：粘贴森空岛 token → 选择 MAA 根目录（含 `MAA.exe` 的那一层）。
不想下载成品也可以按下面的「快速开始」从源码跑。

---

## 功能

| 功能 | 说明 |
|---|---|
| 账号同步 | 粘贴森空岛 token，自动拉取干员、等级、精英化、专精、模组，生成账号配置 JSON |
| 多账号 | 一个 token 绑定多个角色时分别生成；左侧列表一点即切 |
| 练度统计 | 干员数 / 精二 / 满级 / 六星 / 专三 / 模组 / 潜能 / 信赖 |
| 缺卡清单 | 点顶部「缺卡」，按星级列出还没有的干员名字 |
| 作业匹配 | 输入关卡代号（`TL-10`）、活动（`act55side`）、系列（`TR-`）或中文名，逐份比对干员与练度 |
| 快捷活动 | 顶部胶囊列出近期活动，带关卡代号字母（`残照终尽 TL`），点一下直接搜 |
| 作业集 | 单关挑一份，或活动每关自动挑最佳；支持复制 `maa://` 代码 |
| 拖动排序 | 作业集里的作业可以拖动换顺序，顺序就是写进 MAA 的执行顺序 |
| 写入 MAA | 关 MAA → 备份配置 → 下载作业 → 写 `TaskList` → 重启 MAA，全程日志可见 |
| 资源版本 | 资源包带版本号和指纹，更新后首次启动会提示新增干员/关卡与活动 |
| 完全离线 | 关卡表、干员表内置在 `resources/arknights.json`，只有搜作业和同步账号需要联网 |

---

## 快速开始

### 方式一：用 Release 里的压缩包（普通用户）

从上面的「下载」拿 `MAA-PRTS-v2.2.0-win64.zip`，解压后双击 `MAA-PRTS.exe` 即可，不用装 Python。

### 方式二：自己打包

```bat
pip install pywebview pythonnet pyinstaller
python build.py
```

产物在 `dist\MAA-PRTS\`，整个文件夹拷走就能用。

### 方式三：跑源码（需要 Python 3.10+）

```bat
pip install pywebview pythonnet
python backend\main.py
```

调试模式（带 devtools）：

```bat
python backend\main.py --debug
```

---

## 首次启动会做什么

第一次打开会弹一个两步引导：

1. **森空岛 Token** —— 粘贴 token（可加备注）。点击「怎么拿 token」有获取步骤：
   浏览器登录森空岛社区 → F12 → Network → 找发往 `zonai.skland.com` 的请求头里的 `token`。
   程序会把它记到 `skland/tokens.txt`，以后点左上角的刷新按钮即可一键同步全部账号。
2. **MAA 根目录** —— 选包含 `MAA.exe` 的文件夹，点「检测」确认能找到
   `MAA.exe` 与 `config/gui.new.json`。

两步都过了点「保存并同步账号」，窗口会实时打印同步日志，完成后自动切到该账号。
如果暂时没有 MAA，可以先点「稍后设置」——搜作业、复制代码都不受影响，只有「写入 MAA」需要它。

---

## 目录结构

```
MAA-PRTS-1/
├── frontend/            页面（HTML/CSS/JS），由后端本地服务托管
├── backend/             服务端：窗口、HTTP 接口、匹配算法、MAA 读写
├── skland/              ★ 用户数据：token 列表、账号练度 JSON
├── resources/           内置游戏资源包（干员表/关卡表）与打包脚本
├── config/              ★ 用户数据：settings.json、app.log
├── dist/                编译产物（PyInstaller 输出）
├── build.py             打包脚本
├── 启动.bat / 调试启动.bat / 打包.bat
└── README.md
```

每个目录下都有自己的 `README.md`，写明用途和实现细节。

---

## 数据都存在哪

| 内容 | 位置 | 说明 |
|---|---|---|
| token 列表 | `skland/tokens.txt` | 一行一个账号，支持 `备注:token` |
| 账号配置 | `skland/accounts/<昵称> <服务器>.json` | 干员练度 + 缺卡清单 |
| 分支名缓存 | `skland/subprof_cache.json` | 分支中文名边用边学 |
| 应用设置 | `config/settings.json` | MAA 路径、默认配置名、上次选中的账号 |
| 资源版本记录 | `config/gamedata.json` | 上次见到的资源包版本，用来判断要不要提示更新 |
| 运行日志 | `config/app.log` | 超过 2 MB 自动轮转 |

- 上传 GitHub 时这些都会由 `.gitignore` 排除，仓库里只有代码和资源包。
- 换电脑只需要拷 `skland/` 和 `config/`，或者在引导里重新填一次 token。
- 例外只有一个：MAA 根目录本身在你指定的位置，程序只按你填的路径去读写它的 `config/`。

---

## 打包

```bat
python build.py
```

产物：`dist\MAA-PRTS\MAA-PRTS.exe`（onedir，约 30 MB）。

打包只带 `frontend/` 与 `resources/` 两个只读目录。运行时如果 exe 还在项目里，
数据目录会自动定位到项目根；如果把 `dist/MAA-PRTS` 单独拷走，数据就写在 exe 旁边。

---

## 更新游戏资源包

游戏出新干员 / 新关卡后，资源包需要重新生成一次（否则缺卡会漏算新干员）：

```bat
python resources\make_pack.py --excel "D:\ArknightsGameResource\gamedata\excel"
```

生成的新包会带上新的 `version`（生成日期）和 `fingerprint`（内容指纹）。
把它放进 `resources\arknights.json` 即可，不用重新打包程序——
下次启动时程序会发现版本变了，在界面顶部提示：

```
游戏资源已更新到 2026.11.05（原 2026.10.01）
+1 干员 · +7 关卡 · 新活动 残照终尽 TL、通学路 SR …          [知道了]
```

同时新活动会被顶到快捷栏最前面并标上 `NEW`。提示条点「知道了」才消失，
不点就每次启动都提醒一次。详见 `resources\README.md`、`backend\README.md`。

---

## 常见问题

**搜索很慢 / 转圈很久**
活动关卡多时需要逐关去作业站拉数据，十几秒属于正常。单关卡一般 2～4 秒。

**某关卡搜出来是别的关卡的作业**
作业站的 `levelKeyword` 对部分关卡不生效，程序会逐条校验作业的 `stage_name`，
不匹配时改用关卡代号重搜。

**点「写入 MAA」后列表为空**
确认 MAA 根目录填对（存在 `config/gui.new.json`）、写入的配置名存在；
MAA 运行时会回写配置，所以必须先关闭它——这一步程序会自动做。

**token 失效**
森空岛 token 有有效期，失效后同步会打印 401。重新抓一个 token，
把 `skland/tokens.txt` 里对应的那一行替换掉再同步即可。

---

## 说明

本项目只读取森空岛公开接口和 prts.plus 的作业数据，不上传任何账号信息。
作业版权归各作业作者所有，使用时请遵守 MAA 与作业站的相关约定。

以 [MIT License](LICENSE) 开源。仓库里不含任何 token、账号数据与编译产物，
`skland/` 与 `config/` 下只有说明文档，首次运行会自行生成数据文件。
