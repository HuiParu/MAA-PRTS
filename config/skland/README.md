# config/skland —— 森空岛账号数据

这里存放所有跟**你的账号**相关的东西，是程序唯一的账号数据来源。
除了 `tokens.json` 与 `accounts/` 里的 JSON，还会自动生成 `subprof_cache.json`。

> 这些文件都可以随时删除：删掉 `accounts/*.json` 只是丢失缓存，重新同步就回来了；
> 删掉 `tokens.json` 后需要重新粘贴 token。

## tokens.json：加密的多账号 token 列表

token 是账号凭证，明文落盘不放心，所以**每条 token 单独**用 **Windows DPAPI**
（数据保护 API，`CurrentUser` 作用域）加密后存成一个 JSON 列表。多账号就是多条目，
备注是明文（本来也会出现在账号文件名里），token 是密文：

```jsonc
{
  "version": 2,
  "cipher": "dpapi",
  "note": "Windows DPAPI(CurrentUser) 逐条加密：仅本机当前 Windows 用户可解，拷到别的电脑无效。",
  "tokens": [
    {
      "alias": "大号",                    // 备注（可选），用于日志和列表显示
      "addedAt": "2026-11-05T07:40:00",   // 界面添加的时间
      "data": "AQAAANCMnd8BFdERjHoAwE…"   // base64(DPAPI(token))
    },
    { "alias": "小号", "addedAt": "…", "data": "…" }
  ]
}
```

加密的性质（来自 Windows 本身，程序自己不保存密钥）：

- **只能在本机、当前 Windows 用户**下解开；拷到别的电脑、或同机换用户登录，都会解密失败；
- 换电脑迁移时别拷这个文件，到新机器上重新粘贴一次 token 就行（界面「添加账号」）；
- 单条解不开时启动会把整个文件改名为 `tokens.json.broken` 留证并重建空列表，
  在界面里重新添加即可；`tokens.txt.bak` 是从旧版 `skland/tokens.txt` 迁移时
  留下的明文备份，确认没问题后可以手动删掉。

管理 token 不需要手改文件：界面「添加账号」会自动追加进加密列表，
「同步全部」按这个列表逐个刷新；同一 token 只存一份，一个 token 绑定多个
角色时同步会各生成一份账号文件。

## 其他文件

| 文件 | 说明 |
|---|---|
| `accounts/<昵称> <服务器>.json` | 每个角色一份账号配置（练度 + 缺卡），明文 JSON |
| `accounts/作业站/*.json` | 导出的「作业站本地导入」格式（可选，界面上点导出才生成） |
| `accounts/_removed/` | 界面删除账号时的备份 |
| `subprof_cache.json` | 分支中文名缓存，`subProfessionId → 中文`，边同步边学 |

`accounts/*.json` 的完整字段说明（schemaVersion 2）见仓库早期文档或
`backend/core/updater.py` 的 `build_snapshot`；`maa` / `tags` / `note`
是用户字段，重复同步不会覆盖。

## 旧版迁移

数据原来放在项目根的 `skland/`（明文 `tokens.txt`）。升级后首次启动会自动：

1. 把 `skland/` 里的目录与文件搬进 `config/skland/`（新位置已有同名文件则跳过）；
2. 把明文 `tokens.txt` 转成加密 `tokens.json`，原文件改名 `tokens.txt.bak` 留底；
3. 搬空的旧目录随后删除。

## 隐私

- `tokens.json` 是密文，但**不要**把它当作可以随便分享的东西——在能解密的
  那台电脑上它就等于明文 token；
- 账号 JSON 里有游戏 uid、昵称、完整干员练度，上传前注意；
- `.gitignore` 已忽略本目录（除本 README），不会误提交。
