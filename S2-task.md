# S2 内测打磨任务书

> 按 ponytail lite 执行：最小改动、先复用现有、不加依赖与抽象、做完跑一次自检。

## 项目
- 仓库：`C:\Users\BGS06\.dsh\bot\workspace\moments-comment-assistant`
- 当前 main 有 S1 四大模块（src/overlay.py、capture.py、vision.py、main.py），代码红线零命中

## S2 交付物

### 1. BYOK 配置页 `src/config_window.py`
- PyQt 弹窗，从主浮窗右键菜单或设置按钮打开
- 三项输入：`API Base URL`、`API Key`、`Model`，对应 vision.py 的 `VL_API_BASE`、`VL_API_KEY`、`VL_MODEL`
- 保存按钮：写入仓库根 `config.json`（已在 .gitignore）
- 「检测 Key」按钮：用输的配置发一条最小 VL 请求（传 1x1 占位图），返回值非空/非报错即标绿 ✓，否则标红 ✗
- 读已有 config.json 回填字段

### 2. 主入口整合
- `src/main.py` 浮窗加右键菜单或设置按钮，打开配置页
- 启动时尝试 `vision.load_config()`，没配就自动弹配置页

### 3. PyInstaller 打包脚本 `build.spec` 或 `build.py`
- 单 exe：`--onefile --windowed --name "朋友圈评论助手"`
- 包含 `PyQt5`、`pywin32`、`pyperclip`、`openai`、`Pillow` 的 hidden-imports
- 产物落 `dist/`

### 4. README 使用节
在 `## 快速开始` 段下补安装与使用说明：
- `pip install -r requirements.txt`
- 配置 API（三种通道说明，占位 `<!-- 免费通道表由跑腿核验后填入 -->`）
- 运行 `python src/main.py`
- **免责六条段一个字不动**

### 5. `requirements.txt`
列出全部依赖：`PyQt5`、`pywin32`、`pyperclip`、`openai`、`Pillow`

## 写域
- **只写**：`src/config_window.py`、`src/main.py`（改）、`build.spec`、`requirements.txt`、`README.md` 使用节
- **不动**：`src/capture.py`、`src/overlay.py`、`src/vision.py`（除非配置页需要小改 vision.py 的 load_config 路径）
- **不动**：README 免责段（`## ⚠️ 免责声明` 整段）

## 验收
1. 配置页三项可填、可存、可回读
2. 「检测 Key」用无效 key → 红 ✗，有效 key → 绿 ✓
3. `pyinstaller build.spec` 成功，`dist/` 有 exe
4. 浮窗/截图/草稿/剪贴板四断言仍通过