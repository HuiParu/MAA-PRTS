# skland —— 森空岛账号数据

这个目录存放所有跟**你的账号**相关的东西，是程序唯一的账号数据来源。
除了 `tokens.txt` 与 `accounts/` 里的 JSON，这里还会自动生成 `subprof_cache.json`。

> 这些文件都可以随时删除：删掉 `accounts/*.json` 只是丢失缓存，重新同步就回来了；
> 删掉 `tokens.txt` 后需要重新粘贴 token。

## 文件

| 文件 | 说明 |
|---|---|
| `tokens.txt` | token 列表，一行一个账号。「同步全部」时按这个文件逐个刷 |
| `accounts/<昵称> <服务器>.json` | 每个角色一份账号配置（练度 + 缺卡） |
| `subprof_cache.json` | 分支中文名缓存，`subProfessionId → 中文`，边同步边学 |
| `accounts/作业站/*.json` | 导出的「作业站本地导入」格式（可选，界面上点导出才生成） |

## tokens.txt 写法

以 `#` 开头是注释（行尾也可以用「空格 + #」写行内注释），空行忽略。一行支持四种写法：

```
emU/4RpzLSqRC6Z6iW3wK99n                  # 只有 token
杂鱼:emU/4RpzLSqRC6Z6iW3wK99n              # 备注:token（备注只用于日志和 alias）
杂鱼:emU/4Rpz...:杂鱼#5834 官服.json        # 备注:token:指定文件名
杂鱼 emU/4RpzLSqRC6Z6iW3wK99n              # 备注 token（空格分隔，备注可含空格，不能带冒号）
```

- 带 `:` 的行按「第一个冒号前是备注、最后一个冒号后是文件名、中间全部是 token」切分，
  所以备注:token:文件名 这种三段式里 token 本身含 `:` 也没关系。
- 空格写法只对整行没有 `:` 的行生效：最后一段是 token，前面拼起来是备注。
- 同一个 token 出现多次只处理第一次。
- 一个 token 绑定了多个角色时，会按「昵称 服务器」各生成一份，互不覆盖。
- 界面「添加账号」会自动把新 token 追加到这里，不需要手改。

## accounts/*.json 结构

`schemaVersion: 2`。一个角色一份，文件名是「昵称 服务器」，重名自动加 ` (2)`。

```jsonc
{
  "schemaVersion": 2,
  "generator": "MAA-PRTS/2.1",
  "account": {
    "uid": "58061849",
    "nickName": "小卡拉帕鲁灰#6408",
    "alias": "备注",
    "channelName": "官服",
    "level": 120,
    "registerAt": "2019-04-30T11:09:33+08:00",
    "lastOnlineAt": "2026-11-04T17:26:00+08:00",
    "secretary": { "charId": "...", "name": "焰影苇草", "skinName": "博物" }
  },

  "maa":  { "profile": "", "note": "" },   // 用户字段，同步不会覆盖
  "tags": [],                              // 用户字段，同步不会覆盖

  "sync": { "syncedAt": "...", "gameTime": "...", "tokenHint": "tmE0…GgN/" },

  "stats": {
    "charCount": 419, "charTotal": 440, "missingCount": 21,
    "sixStarCount": 125, "sixStarTotal": 141,
    "e2Count": 155, "e2MaxCount": 112, "e1Count": 180, "e0Count": 84,
    "mastery3Count": 209, "moduleCount": 464, "module3Count": 59,
    "byRarity": { "6": 125, "5": 138, "4": 132, "3": 20, "2": 4 },
    "byProfession": { "近卫": 88, "术师": 60, "狙击": 59, "...": 0 },
    "missingByRarity": { "6": 16, "5": 4, "4": 1 },
    "potentialMaxCount": 42, "favorMaxCount": 180, "skinCount": 233
  },

  "chars": [
    {
      "charId": "char_350_surtr", "name": "史尔特尔",
      "rarity": 6, "profession": "近卫", "subProfession": "术战者",
      "elite": 2, "level": 90, "potential": 1, "skillLevel": 7,
      "skills": [{ "id": "skchr_surtr_2", "name": "熔核巨影", "mastery": 3 }],
      "modules": [{ "id": "uniequip_002_surtr", "name": "晶体电子单元", "level": 3, "kind": "模组" }],
      "favor": 200, "skin": { "id": "...", "name": "..." }, "skinCount": 3
    }
  ],

  "missing": [
    { "charId": "char_4017_puzzle", "name": "谜图", "rarity": 6,
      "profession": "辅助", "subProfession": "召唤师" }
  ]
}
```

几个口径：

- **图鉴全集 = 440**：`character_table` 里 469 个 `char_*`，去掉 29 个 `isNotObtainable`
  （剧情/活动限定 NPC）。阿米娅的 2 个升变形态已包含在 469 里（生成资源包时从
  `char_patch_table` 合并进来的），不需要再加。
- **`chars` 按 星级 → 精英 → 等级 降序**，界面直接按这个顺序展示。
- **`missing` 只说明「没有这个干员」**，不涉及任何关卡进度。
- **`maa` / `tags` / `note` 是用户字段**，重复同步不会覆盖，可以自己往里加东西
  （例如把 `maa.profile` 填成某个 MAA 配置名）。

## 隐私

账号 JSON 里有游戏 uid、昵称、完整干员练度。上传 GitHub 前请确认没有提交本目录，
仓库里的 `.gitignore` 已经默认忽略 `skland/tokens.txt`、`skland/accounts/`、`skland/subprof_cache.json`。

要分享配置给朋友，建议只发 `tokens.txt` 以外的部分，或者干脆让对方自己同步一遍。
