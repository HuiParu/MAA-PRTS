# dist —— 编译产物

## 用途

PyInstaller 的输出目录，放可以直接双击运行的发行版。

```
dist/
└── MAA-PRTS/
    ├── MAA-PRTS.exe        主程序
    └── _internal/          运行时（Python 解释器、pywebview、前端页面、资源包）
        ├── frontend/       页面（打包时从 frontend/ 拷入）
        └── resources/      资源包 arknights.json
```

约 30 MB，不需要装 Python，也不需要 WebView2 之外的其他运行时（Win10/11 自带）。

## 生成

```bat
python build.py
```

或双击根目录 `打包.bat`。脚本会重新画图标、清空旧的 `build/` 与 `dist/`，再调 PyInstaller。

## 数据放在哪

**在仓库里直接运行 exe 时**：程序从 exe 目录向上找，发现 `E:\project\MAA-PRTS-1\`
同时有 `frontend/` 和 `backend/`，就把数据写在项目根的 `skland/`、`config/` —— 和源码运行共用一份。

**把 `dist/MAA-PRTS` 整个拷到别处时**：找不到项目结构，数据就写在 exe 同级的
`skland/` 与 `config/`，即插即用。

两种情况下都不会往系统目录或用户目录写东西。

## 注意

- 本目录由脚本生成，不要手改里面的文件（下次打包会被覆盖）。
- `.gitignore` 忽略 `build/`、`build_*/`、`dist/`、`dist_*/`；本文件 `dist/README.md` 是
  已入库的例外（跟踪中的文件不受 ignore 规则影响）。产物不进仓库，发版走 Release 附件。
- 改了 `frontend/` 或 `resources/` 之后必须重新打包，exe 用的是包内的副本。
