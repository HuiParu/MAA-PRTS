# build —— 构建产物

## 用途

仓库里唯一的构建输出目录，由 `打包.bat` / `python build.py` 生成：

```
build/
├── README.md           本说明（入库）
└── MAA-PRTS/           ★ 发布包本体：Release 压缩包解压后的内容
    ├── MAA-PRTS.exe        主程序
    └── _internal/          运行时（Python 解释器、pywebview、前端页面、资源包）
```

构建过程中的中间产物（spec、分析缓存）放在 `build/work/`，打包成功后自动删除；
只有失败时才保留供排查。

`MAA-PRTS/` 约 30 MB，不需要装 Python，也不需要 WebView2 之外的其他运行时
（Win10/11 自带）。发版时把 `build/MAA-PRTS` 压缩成 `MAA-PRTS-v<版本>-win64.zip`
传 Release 即可，包内容与用户下载解压得到的一致。

## 生成

双击根目录 `打包.bat`（或 `python build.py`）。每次打包会先清空旧产物再全量重建，
结束后目录里只剩本文件与 `MAA-PRTS/`。

## 数据放在哪

**无论在仓库里直接运行 exe，还是把 `build/MAA-PRTS` 整个拷到别处**：数据一律写在
exe 同级的 `config/`（账号数据在其 `skland/` 子目录），日志在 exe 同级的 `debug/`，
即插即用。程序不向上找项目根，也不会往系统目录或用户目录写东西。

注意：exe 一旦运行过，`build/MAA-PRTS/` 里就会多出 `config/`、`debug/`（含加密
token）。**压缩发版请用刚构建好的全新产物**，或压缩前先删掉这两个目录。

## 注意

- 本目录除本文件外由脚本生成，不要手改；下次打包会被覆盖。
- `.gitignore` 忽略 `build/*`，仅本文件入库；产物不进仓库，发版走 Release 附件。
- 改了 `frontend/` 或 `resources/` 之后必须重新打包，exe 用的是包内的副本。
