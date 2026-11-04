# config —— 应用配置与日志

## 用途

存程序自己的设置和运行日志。第一次运行时目录是空的，程序会自动创建
`settings.json`（首次保存设置时）与 `app.log`。

## 文件

### settings.json

```jsonc
{
  "maaDir": "D:\\2.game\\MAA-ALL\\MAA-ARK\\MAA-v6.20.1-win-x64",
  "profile": "moren",
  "autoStartMaa": true,
  "lastAccount": "小卡拉帕鲁灰#6408 官服.json"
}
```

| 字段 | 说明 |
|---|---|
| `maaDir` | MAA 根目录（含 `MAA.exe` 与 `config/gui.new.json`）。写入路径时会自动规范化斜杠 |
| `profile` | 默认写入哪个 MAA 配置，下拉框选中的默认项 |
| `autoStartMaa` | 写完作业后是否自动启动 MAA |
| `lastAccount` | 上次选中的账号文件，下次启动直接恢复 |

这个文件可以直接手改；改完要重启程序生效（程序启动时读一次并缓存）。
删掉它等于恢复默认：引导会重新出现，需要再填一次 MAA 目录。

### app.log

每行一条，`[HH:MM:SS] 内容`。记录启动信息、端口、接口异常堆栈、任务结果。
超过 2 MB 自动改名为 `app.log.1` 并重新开始。

排查问题时优先看这个文件：

- 启动失败的 Python 报错会写在这里
- `/api/*` 的异常会带 traceback 最后三行
- 写入 MAA 的每一步也会打到任务日志（界面上能看，但只有这里留档）

### gamedata.json

程序自动生成的「资源版本记录」，用来判断内置游戏资源包有没有更新：

```jsonc
{
  "version": "2026.11.05",          // 上次见到的资源包版本
  "fingerprint": "3af97ae0",        // 上次见到的内容指纹
  "counts": { "chars": 469, "stages": 3647, ... },
  "acts": ["act55side", "act54side", ...],   // 上次见过的活动，用来算「新活动」
  "seenAt": "2026-11-05T01:50:00",
  "pending": null                   // 有更新时是一段 {from,to,delta,newActs}，用户点「知道了」后清空
}
```

- 删掉它 = 下次启动当作首次运行，静默重新记录，**不会弹更新提示**。
- 想再看一次更新提示（测试用）：把 `version` 或 `fingerprint` 改成别的值，重启即可。

## 注意

- 这些文件都不含账号 token 或干员数据，可以安全贴给别人看。
- `.gitignore` 已忽略本目录下的 `settings.json`、`app.log`、`gamedata.json`。
