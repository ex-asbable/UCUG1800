# AI Tutor · UCUG1800

AI Tutor 是在本机运行的单用户复习工具。上传一份课程 PDF 后，应用生成能打开原文的知识点目录。Tutor 根据学生的思路追问，再用一道无提示新题确认具体卡点。复习清单优先显示仍待复习的已确认卡点。

## 在 Windows 上启动

需要 Python 3.12 或更新版本、Node.js 20.19 或更新的 20.x 版本（也可以用 22.12 及之后的 LTS 版本），以及下方两种模型后端中的一种。在仓库根目录运行这些 PowerShell 命令。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
```

### 使用 ChatGPT 登录的 Codex CLI

这是默认后端。终端中应能运行 `codex`。如果尚未登录，运行 `codex login` 并选择 ChatGPT 登录，再检查状态。

```powershell
codex --version
codex login status
$env:AI_TUTOR_PROVIDER = "codex_cli"
.\.venv\Scripts\python.exe -m uvicorn tutor.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 [本机 AI Tutor](http://127.0.0.1:8000/)。右上角会显示当前后端。Codex CLI 使用本机已有授权，模型生成需要联网，并计入账户可用额度。

### 使用模型 API

在启动服务的同一个终端配置支持 Responses API 和 Structured Outputs 的模型。通过本机环境或密钥管理器提供 `AI_TUTOR_API_KEY`。

```powershell
$env:AI_TUTOR_PROVIDER = "api"
$env:AI_TUTOR_API_MODEL = "<你的模型 ID>"
.\.venv\Scripts\python.exe -m uvicorn tutor.main:app --host 127.0.0.1 --port 8000
```

| 环境变量 | 默认值与用途 |
| --- | --- |
| `AI_TUTOR_PROVIDER` | `codex_cli`。可改为 `api`，保存配置后重启服务 |
| `AI_TUTOR_CODEX_BIN` | `codex`。也可指定可执行文件的绝对路径 |
| `AI_TUTOR_API_KEY` | API 模式必填。由本机后端读取 |
| `AI_TUTOR_API_MODEL` | API 模式必填。使用后端账户可用的模型 ID |
| `AI_TUTOR_API_BASE_URL` | `https://api.openai.com/v1`。填包含版本前缀的基础地址，应用会在末尾加上 `/responses` |
| `AI_TUTOR_DATA_DIR` | 仓库根目录下的 `.data`。包含 SQLite 和原始 PDF，可改成本机其他目录 |
| `AI_TUTOR_MODEL_TIMEOUT` | 单次模型请求默认等待 180 秒，支持 10 至 900 秒 |

在 macOS 或 Linux 上可将上面的 `.\.venv\Scripts\python.exe` 换成 `./.venv/bin/python`，`npm.cmd` 换成 `npm`，并用 `export` 设置环境变量。应用按单进程运行，使用同一个数据目录时只启动一个服务实例。

## 复习流程

1. 新建课程并上传文本可选中的 PDF。首轮可以使用开发文档第 8.3 节的假设检验课件。每份文件最多 30 MiB、350 页。
2. 选择一个知识点，点击「开始辅导」，或直接「提一个新问题」。点击出处可检查提取的原文，并跳到 PDF 的物理页。
3. 写下自己的步骤或理由。Tutor 提出疑似卡点时，选单选、文字或 TeX 格式，点击「检查这个卡点」。短题在独立界面作答，提交后显示判定、证据和参考解法。
4. 打开「复习清单」回看已确认的卡点。再完成一道新题并给出关键理由后，相应卡点会移出清单。刷新页面或重启服务后可继续上次的课程和会话。

语言设置同时切换界面和 Tutor。首次查看另一种语言的已有内容时，模型会生成并缓存译文。引用原文、学生的输入、短题和选项 ID、提交结果及复习进度沿用同一份记录。

### PDF 和判分范围

- 当前只接收 PDF。应用按页提取文字层，标记无可读正文的页，支持补传或替换。Word、PowerPoint 和 OCR 留到后续。课件有文字但公式或代码是图片时，Tutor 使用该页实际提取到的内容。
- 单选按选项 ID 判定。文字填空结合已知表达与评分要点。TeX 支持数字、分数、低次多项式和单变量一次等式。无法可靠核对的表达或证据不足的理由会保留为待确认。
- 原始课件、会话、作答和复习记录存放在本机。目录生成会向选定的模型发送按页截取的文本。辅导、出题和判分会发送相关课件片段与所需作答上下文。

## 开发与验收

后端位于 `tutor/`，前端位于 `frontend/`。开发时可在两个终端分别启动 FastAPI 和 Vite。先按上面配置模型，再从仓库根目录执行。

```powershell
# 终端 1
.\.venv\Scripts\python.exe -m uvicorn tutor.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2
npm.cmd --prefix frontend run dev
```

Vite 默认将 `/api` 转发到 `http://127.0.0.1:8000`。使用其他后端端口时设置 `AI_TUTOR_DEV_API`。OpenAPI 定义由服务的 `/openapi.json` 提供。

后端回归使用固定模型输出，覆盖作答状态、格式等价性、模型失败重试、引用版本和重启恢复。设置 `AI_TUTOR_TEST_PDF` 可加跑开发文档中的 125 页课件导入测试。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:AI_TUTOR_TEST_PDF = "C:\path\to\7. Hypothesis Testing.pdf"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd --prefix frontend run build
```

常见故障可在界面的处理进度中查看。模型失败时，从原任务重试可以继续使用已保存的上传或作答。PDF 无文字层时，补传可选中文本的文件。需要迁移数据时，先停止服务，再复制完整数据目录。

[开发文档与手工验收样例](<AI Tutor 开发文档.md>)
