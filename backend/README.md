# backend —— 服务端

## 用途

一个进程同时干三件事：

1. `http.server` 起本地服务，托管 `frontend/` 并提供 `/api/*` 接口
2. 用 pywebview 开一个 WebView2 原生窗口指向它
3. 在后台线程里跑耗时任务（同步账号、写入 MAA），进度通过任务日志接口吐给前端

不依赖 Flask/Django，全部用标准库 + pywebview。

## 文件

| 文件 | 职责 |
|---|---|
| `main.py` | 入口：找端口、起服务、开窗口、日志、原生桥 `Bridge` |
| `core/settings.py` | 路径解析（项目根、skland、config）、`settings.json` 读写 |
| `core/api.py` | 所有 `/api/*` 的实现与路由表，静态文件 MIME 表 |
| `core/accounts.py` | 读 `skland/accounts/*.json`、token 落盘、后台同步 |
| `core/updater.py` | token → 账号配置的完整构建（练度、缺卡、统计、增量对比） |
| `core/skland.py` | 森空岛鉴权链：token → grant → cred → 签名请求 → 绑定/角色数据 |
| `core/copilot.py` | 作业站接口 + 干员要求匹配算法 |
| `core/resources.py` | 读 `resources/arknights.json`：关卡索引、干员表、技能/模组名、活动代号前缀 |
| `core/version.py` | 版本管理：程序版本、内置资源包版本、资源更新检测与提示 |
| `core/maa.py` | MAA 进程控制、`gui.new.json` 读写、作业文件下载 |
| `core/tasks.py` | 内存任务表：状态、日志、结果，供前端轮询 |

## 启动流程

```
main()
 ├─ find_port()            8787 起，被占用就 +1（Windows 用独占绑定，防止双开抢端口）
 ├─ Thread: serve(port)    ThreadingHTTPServer，HTTP/1.1 长连接
 ├─ 建窗口 webview.create_window(js_api = Bridge())
 └─ webview.start()        窗口关闭后 shutdown 并退出进程
```

日志同时写 `config/app.log` 和控制台，超过 2 MB 轮转为 `app.log.1`。

## 路径规则（重点）

`settings.py` 在导入时算一次，之后全进程复用：

| 用途 | 源码运行 | 打包运行 |
|---|---|---|
| 只读资源 | 项目根 | `sys._MEIPASS`（PyInstaller 解包目录） |
| 可写数据 | 项目根 | 从 exe 目录向上找第一个含 `frontend/` + `backend/` 的目录；找不到就用 exe 目录 |

所以：在仓库里跑 exe，数据和源码共用一份（都在项目根的 `skland/`、`config/`）；
把 `dist/MAA-PRTS` 单独拷给别人，数据就落在 exe 旁边。程序**不会**写项目目录以外的地方。

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/bootstrap` | 一次性拉：设置、账号列表、MAA 状态、活动、路径、资源包信息、资源版本、首启标记 |
| GET | `/api/accounts` | 账号列表（含每个账号的统计摘要） |
| GET | `/api/account?file=` | 单个账号完整配置：account / stats / missing / chars |
| POST | `/api/account/refresh` | 同步账号。带 `token` 同步单个并记入 `tokens.txt`；不带则按 `tokens.txt` 全部同步 |
| GET | `/api/search?q=` | 搜索作业，返回 stage/activity 两种结构 |
| GET | `/api/op?id=` | 作业详情（干员与要求、动作数、`maa://` 代码） |
| GET | `/api/gamedata` | 资源包版本状态（含 `pending` 更新提示） |
| POST | `/api/gamedata/ack` | 清掉待提示的资源更新 |
| GET | `/api/maa/status` | MAA 是否运行、配置列表、当前配置 |
| GET | `/api/maa/probe?dir=` | 检测目录是不是 MAA 根目录（引导/设置用） |
| POST | `/api/maa/apply` | 写入作业集：关 MAA → 备份 → 下载 → 写 TaskList → 重启 |
| GET | `/api/task?id=&since=` | 任务状态与增量日志 |

所有响应统一为 `{"ok": true, "data": ...}` 或 `{"ok": false, "error": "..."}`。

## 版本管理（`version.py`）

分两层，互不相干：

| | 来源 | 用途 |
|---|---|---|
| 程序版本 `APP_VERSION` | 代码里写死 | 日志、设置页、请求头 `Server` |
| 资源版本 | `resources/arknights.json` 的 `version` + `fingerprint` | 判断游戏数据有没有变 |

资源包由 `make_pack.py` 生成时会写入 `version`（生成日期，如 `2026.11.05`）和
`fingerprint`（内容指纹，同一天多次生成也能区分）。`version.check()` 把它和
`config/gamedata.json` 里记的「上次见到的版本」比对：

| 情况 | 行为 |
|---|---|
| 没有 `gamedata.json`（首次运行） | 静默记下当前版本，不提示 |
| 版本与指纹都一致 | 什么都不做 |
| 不一致 | 写一条 `pending`：新增干员/关卡数 + 新活动列表，前端顶部出现提示条 |

`pending` 会一直留着，直到用户点「知道了」（`/api/gamedata/ack`）——
不点就每次启动都提醒一次，避免用户错过。

资源包装载顺序是「项目目录 `resources/arknights.json` → 程序内置那份」，
所以想更新游戏数据，把新的 `arknights.json` 覆盖到项目 `resources/` 里就行，
不用重新打包；下次启动就会看到更新提示，新活动也会排到快捷栏最前面。

## 匹配算法（`copilot.py`）

逐份作业、逐个干员比对，判定分四档：

| 结果 | 含义 |
|---|---|
| `ready` | 干员都有、练度都够，可以直接抄 |
| `borrow` | 只差 1 个干员（可借），其余满足 |
| `train` | 人齐但练度/专精/模组不够 |
| `blocked` | 缺 2 人以上，或超过 13 人队伍上限 |

练度不按「等级数值」直接比，而是折算成**进度分**：先用干员星级 + 等级推断其应有的精英阶段，
再按 `精二 / 精一 / 精零` 分段加权，避免「精一 70 级」被误判为高于「精二 1 级」。

两个容易写错的地方，代码里有注释：

- **技能序号在作业条目顶层**（`op.skill`），不在 `requirements` 里。取错会让所有「专三二技能」
  的作业被判成练度不足。
- **作业站 `levelKeyword` 对部分关卡不生效**（例如 `tr_04` 会返回全站热门作业），
  所以每份作业都要校验 `content.stage_name`，不匹配时改用 `document=<关卡代号>` 重搜。

## MAA 写入流程（`maa.py`）

```
taskkill MAA.exe
  → 备份 config/gui.new.json.bak-app-<时间戳>
  → 下载作业 JSON 到 config/copilot/<关卡>_<id>.json
  → 写 Configurations.<配置名>.Copilot.TaskList
      Name = 关卡代号（悖论模拟模式用干员名，此处是关卡）
      CopilotId / FilePath / IsChecked / Index
  → 启动 MAA.exe（可在界面关掉）
```

MAA 运行时会周期性回写配置文件，所以必须先关进程再改，否则改动会被覆盖。

## 依赖

- Python 3.10+
- `pywebview`（自带 pythonnet + WebView2；WebView2 Runtime 是 Win10/11 系统组件）
- 打包用 `pyinstaller`

其余全部是标准库。
