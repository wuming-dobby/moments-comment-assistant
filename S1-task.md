# S1 Vibe 原型任务书

> 按 ponytail lite 执行：最小改动、先复用现有、不加依赖与抽象、做完跑一次自检。

## 项目

- 仓库：`C:\Users\BGS06\.dsh\bot\workspace\moments-comment-assistant`
- GitHub：https://github.com/wuming-dobby/moments-comment-assistant
- 语言：Python 3.10+
- 依赖：PyQt5、pyperclip、openai、Pillow、pywin32

## 交付物

在 `src/` 下实现四个模块，在 `tests/` 下写验证脚本：

### 1. 浮窗模块 `src/overlay.py`
- 一个 PyQt 置顶无边框小窗（`WindowStaysOnTopHint | FramelessWindowHint | Tool`）
- 包含一个「生成评论」按钮
- 轮询微信主窗口状态（`pywin32` 或 `win32gui`，窗口标题含"微信"，类名 `WeChatMainWndForPC`）：窗口激活（前景）→ 浮窗显示；最小化或失焦 → 浮窗隐藏
- 浮窗位置：屏幕右下角，不遮挡朋友圈内容区

### 2. 截图模块 `src/capture.py`
- 使用 Win32 GDI（`win32gui` + `win32ui`）截取微信主窗口客户区
- 保存为 PNG 到 `screenshots/` 目录（文件名 `capture_YYYYMMDD_HHMMSS.png`）
- 返回文件路径

### 3. VL 调用模块 `src/vision.py`
- 读环境变量 `VL_API_BASE`、`VL_API_KEY`、`VL_MODEL`（或从 `config.json` 读）
- 用 openai 库调用 OpenAI 兼容 Vision API，传截图文件
- 系统提示词：「你是一个朋友圈评论助手。看到以下朋友圈截图，请生成一条真诚、自然、不做作的中文评论草稿。只返回评论文本，不要加前缀说明。」
- 返回评论文本

### 4. 主入口 `src/main.py`
- 串联：浮窗显示 → 点击按钮 → 截图 → 调 VL → 草稿写入剪贴板（pyperclip）
- 简单的错误处理：截图失败/API 失败弹 toast 提示

### 5. `tests/test_pipeline.py`
- 模拟：无微信窗口时浮窗不显示；有 API 配置时调 VL 返回非空文本

## 写域

- **只写**：`src/`、`tests/`
- **不动**：`README.md`、`LICENSE`、`.gitignore`、`S1-task.md`

## 验收断言（编码会跑）

1. 微信窗口激活 → 浮窗出现，最小化 → 浮窗隐藏
2. 点击按钮 → 生成 PNG 截图（非空，分辨率=窗口客户区）
3. 配置 API 后 → 返回非空评论草稿文本
4. 草稿在系统剪贴板可粘贴出
5. `grep -riE "inject|hook|decrypt|upload|server" src/` 零业务命中（URL 里的 server 不算）

## 红线

- 不做 UIA（不调 `uiautomation`、不写 `SendInput`）
- 不碰微信进程内存（不调 `ReadProcessMemory`、`WriteProcessMemory`）
- 不上传数据到第三方服务器（只有用户自己配的 VL API 调用）
- 不动 README 合规段