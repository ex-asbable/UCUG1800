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

Windows 上应用先检查启动终端的 PATH，再查找已安装的 Codex 桌面版附带的 CLI。若界面仍报告找不到 CLI，请在启动服务的同一个终端运行 `Get-Command codex -CommandType Application`。如果已知道可执行文件的位置，设置 `$env:AI_TUTOR_CODEX_BIN = "C:\path\to\codex.exe"` 后重启。使用该路径运行 `& $env:AI_TUTOR_CODEX_BIN login status` 可核对登录状态。

### 使用模型 API

点击右上角的模型按钮，在「模型设置」中选择「模型 API」，填写 API 基础地址及密钥，点击「加载模型列表」，再选择支持 Responses API 和 Structured Outputs 的模型并应用。处理中的任务完成后即可切换。切换后可从处理进度重试之前失败的任务。

页面设置在本次服务运行期间有效，输入的密钥只保存在服务内存中。需要让服务启动时直接使用 API 模式，可在同一个终端设置环境变量后启动。

```powershell
$env:AI_TUTOR_PROVIDER = "api"
$env:AI_TUTOR_API_MODEL = "<你的模型 ID>"
$env:AI_TUTOR_API_KEY = [System.Net.NetworkCredential]::new("", (Read-Host "API 密钥" -AsSecureString)).Password
.\.venv\Scripts\python.exe -m uvicorn tutor.main:app --host 127.0.0.1 --port 8000
```

| 环境变量 | 默认值与用途 |
| --- | --- |
| `AI_TUTOR_PROVIDER` | 服务启动时使用的模型后端，默认为 `codex_cli`，可设为 `api` |
| `AI_TUTOR_CODEX_BIN` | `codex`。也可指定可执行文件的绝对路径 |
| `AI_TUTOR_CODEX_MODEL` | Codex CLI 的启动模型 ID。留空使用 CLI 默认模型 |
| `AI_TUTOR_CODEX_REASONING_EFFORT` | Codex CLI 的启动思考强度。留空使用后端默认值 |
| `AI_TUTOR_API_KEY` | 由本机后端读取。使用默认 OpenAI 地址时也可读取 `OPENAI_API_KEY` |
| `AI_TUTOR_API_MODEL` | API 模式必填。使用后端账户可用的模型 ID |
| `AI_TUTOR_API_REASONING_EFFORT` | API 的启动思考强度。留空时由 API 采用默认设置 |
| `AI_TUTOR_API_BASE_URL` | 默认为 `https://api.openai.com/v1`。可填含版本前缀的基础地址，或以 `/responses` 结尾的完整接口地址 |
| `AI_TUTOR_DATA_DIR` | 仓库根目录下的 `.data`。包含 SQLite 和原始 PDF，可改成本机其他目录 |
| `AI_TUTOR_MODEL_TIMEOUT` | 单次模型请求默认等待 180 秒，支持 10 至 900 秒 |

在 macOS 或 Linux 上可将上面的 `.\.venv\Scripts\python.exe` 换成 `./.venv/bin/python`，`npm.cmd` 换成 `npm`，并用 `export` 设置环境变量。应用按单进程运行，使用同一个数据目录时只启动一个服务实例。

### 选择模型与思考强度

打开右上角的「模型设置」并选择后端。Codex CLI 通过其模型目录提供当前账户可选的模型和对应的思考强度。模型 API 从填写的地址读取 `/models`，只显示该端点返回的模型。思考强度优先读取模型的能力信息，缺少信息时通过输入 token 计数接口检查选中的模型支持哪些档位。服务无法提供或确认档位时，可以使用后端默认强度。两种后端各自保留本次服务中的选择。 [Codex 模型目录](https://learn.chatgpt.com/docs/app-server#models) · [模型 API](https://developers.openai.com/api/reference/resources/models/methods/list) · [输入 token 计数](https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens/methods/count)

程序可读取 `GET /api/v1/runtime/status`，通过 `POST /api/v1/runtime/models` 读取模型目录，并通过 `POST /api/v1/runtime/model-efforts` 补查 API 模型的思考强度。通过 `PATCH /api/v1/runtime/settings` 更新空闲服务的配置。Codex CLI 使用 `codexModel` 和 `codexReasoningEffort`，API 使用 `apiModel` 和 `apiReasoningEffort`。省略字段保留现值，向思考强度传 `null` 恢复后端默认值。

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

更新代码后，重新构建前端并重启 FastAPI，再刷新浏览器。更换数据目录后，应用会回到当前目录中可用的课程。

[开发文档与手工验收样例](<AI Tutor 开发文档.md>)
