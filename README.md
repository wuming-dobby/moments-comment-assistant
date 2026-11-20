# 朋友圈评论助手 Moments Comment Assistant

> PC 端浮窗工具：截图微信朋友圈 → 视觉模型识别 → LLM 生成评论草稿 → 复制到剪贴板，**人工粘贴、人工发送**。

## ⚠️ 免责声明与使用须知

本项目为个人学习研究性质的开源工具，与腾讯公司无任何关联，未经腾讯授权。

1. **非官方工具**：本项目通过截图方式读取朋友圈内容，属于微信协议外的第三方辅助工具。使用本工具违反《腾讯微信软件许可及服务协议》《微信个人账号使用规范》，账号可能被限制功能或封停，并可能连带影响微信支付等功能。**使用即视为已知悉并自担该风险。**
2. **仅限本人账号**：本工具仅在你本人已登录的微信 PC 客户端上使用，不索取账号密码，不含支付功能。
3. **禁止滥用**：严禁用于商业营销、批量互动、多开、自动加好友、抓取他人数据、代运营等用途。评论草稿均由人工确认后手动发送。
4. **数据不经手本项目方**：本项目无自有服务器、不收集任何数据；截图会发送至**你自行配置的模型 API**（BYOK），请自行评估所选服务商的隐私政策。
5. **不做风控规避**：本工具不实现任何"防封号""绕过检测"能力，也不以此为卖点。
6. **随时可能下架**：本项目可能因平台投诉或法律原因随时移除，请知悉。

---

## 快速开始

1. 安装依赖（Python 3.10+）：

   ```
   pip install -r requirements.txt
   ```

2. 运行：

   ```
   python src/main.py
   ```

3. 配置 API：首次启动会自动弹出配置页（之后在浮窗上点右键 →「设置 API…」可随时修改）。填三项后先点「检测 Key」，标绿 ✓ 再保存：

   | 字段 | 说明 |
   |---|---|
   | API Base URL | OpenAI 兼容接口地址；Ollama 本地填 `http://localhost:11434/v1` |
   | API Key | 服务商控制台获取（Ollama 可随便填） |
   | Model | 视觉模型名，如 `Qwen/Qwen2.5-VL-7B-Instruct`、`GLM-4.6V-Flash` |

   配置保存在仓库根 `config.json`（已在 .gitignore，不会提交）。可选免费通道（2026-11 现状，以官方价格页为准）：

   | 通道 | 免费视觉模型 | 说明 |
   |---|---|---|
   | 智谱 | **GLM-4.6V-Flash** | 输入/输出/缓存全免费，通用视觉理解，首选 |
   | 硅基流动 | PaddleOCR-VL-1.5 | 仅 OCR 型，理解力弱，作降级备选 |
   | Ollama 本地 | qwen3-vl / qwen2.5vl / minicpm-v | 零联网零 key，7B 需约 8–10 GB 显存 |

4. 打包单文件 exe（可选）：

   ```
   pip install pyinstaller
   pyinstaller build.spec
   ```

   产物在 `dist/朋友圈评论助手.exe`。

## API 配置（BYOK）

本项目不内置 API Key、不中转数据。免费通道详见上方「快速开始」第 3 步的表格。

注册入口：智谱 [open.bigmodel.cn](https://open.bigmodel.cn) ｜ 硅基流动 [siliconflow.cn](https://siliconflow.cn) ｜ Ollama [ollama.com](https://ollama.com)。

> 以上免费额度以 2026-11 官方价格页为准（跑腿核验），如有变动请提 Issue。本项目不打包 key、不中转数据、不做多账号轮询。

## 技术栈

- Python + PyQt（浮窗）+ GDI（截图）
- OpenAI 兼容 Vision API
- 零注入、零 Hook、零数据库解密

## License

Apache-2.0