# AI Tutor · UCUG1800 · v0.1.0

AI Tutor 是在本机运行的单用户学习软件。导入课件后，应用会生成带原文出处的知识点目录。选择一个知识点即可开始对话辅导或生成复习讲解稿。通过无提示短题确认的卡点会进入复习清单。

## 安装 Windows 桌面版

从 [GitHub Release](https://github.com/ex-asbable/UCUG1800/releases/tag/v0.1.0) 下载并运行 Windows x64 安装包 `AI-Tutor-Setup-0.1.0-x64.exe`，安装后从开始菜单打开 **AI Tutor**。安装包自带界面和本机服务。生成目录、辅导和讲解稿仍需可用的模型后端。可以使用本机已经通过 ChatGPT 登录的 Codex CLI，或打开右上角的「模型设置」配置兼容 Responses API 的服务。

### 软件更新

Windows x64 桌面版启动后会检查 GitHub 上的新正式版本，运行期间每 6 小时检查一次。也可从顶部「软件更新」手动检查。发现新版后，点击「下载安装并重启」，应用会下载 Windows x64 安装包、校验其 SHA-256，并安装、重新打开。

### 导入和复习

1. 创建或选择课程，点「导入文件夹」，选中存放课件的目录。应用递归导入子文件夹，保留相对路径和原件，然后更新知识点目录。也可以用「上传 PDF」补传单份课件。
2. PDF、PPTX、DOCX、Markdown、TeX 和常见纯文本格式可提取正文。AI 可分析 PDF 中的图片、矢量图和扫描页，PPTX 与 DOCX 内嵌的常见位图，以及通过文件夹导入的 PNG、JPEG、WebP、GIF、BMP 和 TIFF。处理这些课件时，课件列表会显示「需要多模态模型」。如果当前模型不支持图片输入，请在「模型设置」切换模型，再从「处理进度」重试。每份文件上限为 30 MiB，每批上限为 1,000 份和 512 MiB。
3. 在知识点页点击「复习」，AI 会直接生成含 Markdown 排版、TeX 公式和课件出处的讲解稿。点击「另存为 Markdown」选择本机保存位置。讲解稿按知识点、课件版本和语言保存，关闭软件后可以重新打开。

### 从网页 MVP 迁移数据

桌面版默认使用 `%APPDATA%\AI Tutor\data`。先关闭桌面版和旧版服务，再从旧版的 `.data`（或之前配置的 `AI_TUTOR_DATA_DIR`）复制完整数据目录到桌面版的数据位置。对于已有桌面数据，先备份，并选择一个版本的数据目录使用。也可以在启动桌面版前设置 `AI_TUTOR_DATA_DIR`，直接指定已有数据目录。课程、课件、会话、短题和卡点记录会沿用。

### 构建安装包

在 Windows x64 上准备 Python 3.12+、Node.js 22.12+ 和 PowerShell 7。在仓库根目录执行以下命令。生成的安装包位于 `dist/release/AI-Tutor-Setup-0.1.0-x64.exe`。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r desktop/requirements.txt
pwsh -NoProfile -File desktop/build.ps1
```

## 开发模式

可通过浏览器运行开发版。需要 Python 3.12+ 和 Node.js 20.19+ 或 22.12+。在仓库根目录运行下面的命令。

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

Windows 上应用会比较终端 PATH 中的 CLI 和 Codex 桌面版附带的 CLI，自动选用版本较新的安装。模型目录和辅导使用同一个 CLI。模型设置会显示实际读取目录的 CLI 版本，悬停可查看路径。

若要指定安装，可在启动服务的终端设置 `$env:AI_TUTOR_CODEX_BIN = "C:\path\to\codex.exe"` 后重启。若该变量已指向旧安装，可用 `Remove-Item Env:AI_TUTOR_CODEX_BIN` 恢复自动选择，再重启服务。

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
| `AI_TUTOR_DATA_DIR` | 桌面版默认为 `%APPDATA%\AI Tutor\data`，开发版默认为仓库下的 `.data`。包含 SQLite 和课件原件 |
| `AI_TUTOR_MODEL_TIMEOUT` | 单次模型请求默认等待 180 秒，支持 10 至 900 秒 |

在 macOS 或 Linux 上可将上面的 `.\.venv\Scripts\python.exe` 换成 `./.venv/bin/python`，`npm.cmd` 换成 `npm`，并用 `export` 设置环境变量。应用按单进程运行，使用同一个数据目录时只启动一个服务实例。

### 选择模型与思考强度

打开右上角的「模型设置」并选择后端。Codex CLI 通过其模型目录提供当前账户可选的模型和对应的思考强度。模型 API 从填写的地址读取 `/models`，只显示该端点返回的模型。思考强度优先读取模型的能力信息，缺少信息时通过输入 token 计数接口检查选中的模型支持哪些档位。服务无法提供或确认档位时，可以使用后端默认强度。两种后端各自保留本次服务中的选择。 [Codex 模型目录](https://learn.chatgpt.com/docs/app-server#models) · [模型 API](https://developers.openai.com/api/reference/resources/models/methods/list) · [输入 token 计数](https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens/methods/count)

程序可读取 `GET /api/v1/runtime/status`，通过 `POST /api/v1/runtime/models` 读取模型目录，并通过 `POST /api/v1/runtime/model-efforts` 补查 API 模型的思考强度。通过 `PATCH /api/v1/runtime/settings` 更新空闲服务的配置。Codex CLI 使用 `codexModel` 和 `codexReasoningEffort`，API 使用 `apiModel` 和 `apiReasoningEffort`。省略字段保留现值，向思考强度传 `null` 恢复后端默认值。

## 复习流程

1. 新建课程并上传 PDF。扫描页需要支持图片输入的多模态模型。首轮可以使用开发文档第 8.3 节的假设检验课件。每份文件最多 30 MiB、350 页。
2. 选择一个知识点，点击「开始辅导」，或直接「提一个新问题」。点击出处可检查提取的原文，并跳到 PDF 的物理页。
3. 写下自己的步骤或理由。Tutor 提出疑似卡点时，选单选、文字或 TeX 格式，点击「检查这个卡点」。短题在独立界面作答，提交后显示判定、证据和参考解法。
4. 打开「复习清单」回看已确认的卡点。再完成一道新题并给出关键理由后，相应卡点会移出清单。刷新页面或重启服务后可继续上次的课程和会话。

语言设置同时切换界面和 Tutor。首次查看另一种语言的已有内容时，模型会生成并缓存译文。引用原文、学生的输入、短题和选项 ID、提交结果及复习进度沿用同一份记录。

### 课件和判分范围

- PDF 按物理页引用，PPTX 按幻灯片引用，DOCX 和纯文本按文本段落引用。DOCX 内嵌图片另计为独立段落。点击引用可查看「AI 图片解读」和原件。PDF 支持补传或替换。要分析旧版已导入课件的图片，请重新导入或替换 PDF。
- 单选按选项 ID 判定。文字填空结合已知表达与评分要点。TeX 支持数字、分数、低次多项式和单变量一次等式。无法可靠核对的表达或证据不足的理由会保留为待确认。
- 原始课件、会话、作答和复习记录存放在本机。导入时，检测到视觉内容的 PDF 页面或提取的图片会发送给选定的模型，结果保存在本机。目录生成、讲解稿、辅导、出题和判分会发送相关的课件文本、图片解读和任务所需上下文。

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

常见故障可在界面的处理进度中查看。模型失败时，从原任务重试可以继续使用已保存的上传、图片解读或作答。扫描页清晰度不足时，可以补传更清晰的版本。需要迁移数据时，先停止服务，再复制完整数据目录。

更新代码后，重新构建前端并重启 FastAPI，再刷新浏览器。更换数据目录后，应用会回到当前目录中可用的课程。

[开发文档与手工验收样例](<AI Tutor 开发文档.md>)
