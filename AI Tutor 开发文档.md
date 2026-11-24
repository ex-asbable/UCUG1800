# AI Tutor 开发文档 / AI Tutor Development Draft

[简体中文](#zh-hans) · [English](#en) · [界面文案 / UI copy](#ui-copy)

<a name="zh-hans"></a>

## 简体中文

版本 0.1 · 开发初稿

AI Tutor 面向使用个人课件复习备考的学生。学生上传课程材料后，系统自主分析课件，生成知识点目录、讲解、例题和练习。学生可以从目录进入辅导，也可以直接提出自己的问题。Tutor 先了解学生的思路，再用一道无提示短题确认疑似卡点，据此更新个人复习顺序。

目前已有用户调研和使用演示数据的界面截图。界面可作为交互参照，产品能力以真实课件和真实作答的验证结果为准。

### 1. 产品目标与首版范围

#### 1.1 首版交付

- **交付方式**为本机可运行的单用户 Web 应用。学生可以用真实课件完成从上传到复习的主流程，保存的数据在刷新页面和重启服务后仍可继续使用。
- **当前课件格式**为 `.pdf`。以可提取的正文为输入，扫描页或只有截图的页面标出对应位置并提示补传可读材料。Word 和 PowerPoint 格式留到后续迭代。
- **语言**方面，界面提供简体中文和 English。一个语言设置同时控制界面文案和 Tutor 输出。课件、提问和作答可使用其他语种或混排。
- **作答方式**为选择题、文字填空和 TeX 填空。接口草案以单选题起步。Tutor 对话区另提供文字输入，学生可自行提问和描述思路。
- **数据与模型**方面，课件、目录、对话、作答和进度保存在本机。模型后端可选择线上模型 API 或本机已通过 ChatGPT 登录的 Codex CLI。每轮按当前任务传入所需的课件片段和作答。

#### 1.2 用户任务

| 用户任务 | 首版交付结果 | 需求依据 |
| --- | --- | --- |
| 看清课程内容，决定从哪开始复习 | 自动生成可跳转到课件出处的目录。学生作答后，优先显示已确认的薄弱知识点 | 22/31 位答卷者认为知识点太多。4 位受访者中有 3 位参考作业表现决定复习重点 |
| 弄清自己具体没懂哪条概念或哪一步 | Tutor 能结合学生给出的步骤与理由建立判断，并通过一道无提示短题验证 | 22/32 位答卷者遇到过 AI 没理解自己的疑问。28/32 位希望 AI 指出具体没掌握的步骤或概念 |
| 核对讲法与课件是否一致 | 讲解显示可打开的课件出处。材料缺口和必要的前置补讲有清楚的标记 | 21/32 位答卷者遇到过 AI 解释与教材有出入。1 位受访者希望工具补充缺失知识 |

需求证据来自项目的问卷和看图访谈。试运行重点验证找到复习内容的用时和卡点判断的准确性。一个学生使用自己的课件和作答，就能完成整套复习流程。

系统按课件内容与作答方式组织辅导。公式变换、概念解释和程序理解可以使用不同的验证办法，共用上传、生成目录、追问、独立检查和复习排序流程。

### 2. 名词与界面

| 名词 | 含义 |
| --- | --- |
| 课程 | 学生的个人复习空间，包含本课材料、生成的 Tutor、对话和复习记录 |
| 原始目录 | 材料中可确认的章节目录或教学大纲 |
| 复习目录 | AI 根据实际材料和能确认的原始目录生成的知识点导航 |
| 课件出处 | 可定位到具体材料版本及其 PDF 页码、幻灯片序号或 Word 段落位置的引用 |
| 材料缺失 | 已知目录列出了一个主题，现有材料无法提供该主题的正文依据 |
| 前置知识补充 | 已知后续内容确实要用到、现有课件却未解释的知识，附上应用位置 |
| 疑似卡点 | Tutor 从学生作答或解释中发现的待验证判断 |
| 已确认卡点 | 无提示短题复现了同一理解问题，有作答证据可供回看 |

#### 2.1 页面与主要操作

| 区域 | 用户操作 | 页面反馈 |
| --- | --- | --- |
| 课程入口 | 创建课程、上传或补传本课材料 | 显示上传、解析和生成状态，以及失败后可以采取的操作 |
| 知识点目录 | 选主题，查看课件出处或缺失项 | 显示主题结构、已引用材料及当前复习状态 |
| Tutor 区域 | 提交尝试、解释理由或提出自己的新问题 | 看到针对当前卡点的追问、按需提示和课件依据 |
| 独立检查 | 使用题干和对应的选项或输入框完成一题 | 提交后显示结果、判断理由和对应知识点 |
| 复习清单 | 进入优先复习的主题，回看判断依据 | 显示确认的卡点、最近相关作答和重新练习入口 |
| 语言设置 | 选择简体中文或 English | 界面及正在查看的 Tutor 内容使用同一种语言，重新打开应用时恢复选择 |

界面参照 [AI Tutor 应用截图](ai-tutor-screenshot.png)。截图中的课件、页码和对话为演示数据。首版答题区按本文约定提供选项、文字输入和 TeX 输入及预览。

#### 2.2 界面与 Tutor 语言

- 应用使用一个持久化偏好字段 `locale`，支持 `zh-Hans` 和 `en`。初次使用默认简体中文。学生可从全局的 [语言设置](#ui-copy) 切换。
- 界面按钮、导航、状态和错误提示采用双语文案资源。目录名称、讲解、追问、题干、选项、反馈及卡点说明均按同一个 `locale` 生成。课件语种和学生输入语种可以与界面语种不同。
- 切换后即时更新界面文案。当前课程及会话按需加载或生成所选语言的 Tutor 内容，并缓存供下次使用。显示文本就绪前，使用所选语言提示加载。保存课件引用原文、TeX、学生原始作答及既有复习记录。
- 中英文内容沿用同一知识点、卡点、短题、选项、填空和作答 ID。切换语言时保持题意、正确答案、已填内容、判断结果和复习进度。涉及原文措辞或学科术语的题目可以保留必要的原文。

### 3. 课件生成 Tutor

#### 3.1 导入和分析

1. 学生创建或打开课程，提交一份或多份课件。系统回显文件名和处理状态。
2. 系统按文档段落、页或幻灯片提取正文和可识别的结构，保留章节、定义、示例、可读取的公式及其位置。识别不清的片段保留相应位置，方便学生定位和补充。
3. 系统优先使用课件或教学大纲中可确认的目录，也可以根据正文推断主题结构。推断的主题带着实际正文出处进入复习目录，顺序尽量沿用课件顺序。
4. AI 为有内容依据的主题生成复习入口，包括学习目标、短讲解或例题以及可开始的诊断问题。材料缺失的条目可从目录打开补传入口。
5. 生成后检查引用的材料和位置是否存在。具备依据的部分可以先供学生复习，处理失败的文件继续显示状态并允许重试。

#### 3.2 格式、语言与原文定位

| 文件 | 处理方式 | 引用位置 |
| --- | --- | --- |
| `.pdf` | 在本机按物理页提取文本 | 从 1 开始的物理页号 |

后续迭代的 Office 格式处理方式如下。

| 文件 | 处理方式 | 引用位置 |
| --- | --- | --- |
| `.docx` | 在本机读取标题、段落和可读表格 | 标题路径和段落或表格序号 |
| `.doc` | 在本机转换为 `.docx`，保留原文件和转换后的版本 | 原文件名及转换后文档的标题和段落位置 |
| `.pptx` | 在本机按幻灯片读取标题、文本框和可读表格 | 幻灯片序号 |
| `.ppt` | 在本机转换为 `.pptx`，保留转换状态 | 原文件名及转换后幻灯片序号 |

正文用 Unicode 保存，并保留原文、专用术语和公式符号。课程中可以混用语种。Tutor 讲解使用应用所选语言，引用仍显示课件原文。

扫描页、只有截图且缺少正文的 PDF 页，以及解析失败的页显示「正文不可读取」和对应位置。含可读页的课件可以继续生成 Tutor。如果所有正文都不可用，界面引导学生补传文件或相关页，待取得可读材料后再生成。

#### 3.3 材料缺口

| 可见条件 | Tutor 的行为 | 界面展示 |
| --- | --- | --- |
| 有足够课件正文 | 以相应页或幻灯片为依据生成辅导 | 显示引用，学生可打开出处 |
| 原始目录中能确认主题，正文缺失 | 保留该主题并提示上传相应材料 | 显示「材料缺失」、具体主题和补传入口 |
| 某部分材料和原始目录都无法确认 | 根据已知课件继续生成复习目录和辅导 | 展示现有课件支持的主题 |
| 已知后续内容依赖一项课件没解释的前置知识 | 结合后续题目或推导确定依赖，补讲到足以继续理解的程度 | 标为「前置知识补充」，指出当前缺少的课件依据和后续应用位置 |
| 整份文件读不到可用内容 | 保留处理状态，引导学生提供可读课件或相关页面 | 告知受影响文件及可重试的操作 |

例如，讲义从 $(x-2)(x-3)=0$ 直接跳到两个根，却没有说明这一步的依据。Tutor 应补讲零积定律，并将补讲关联到这页推导。引用对应的是**后续用到定律的位置**，补充解释单独标注其来源性质。

学生自提题可以是课件中没有预先列出的新问题。Tutor 从学生提供的题目、作答和相关课件寻找依据。与当前课程的联系不清楚时，先确认相关主题或请求补充材料。

#### 3.4 补传与更新

- 新材料解析成功后，重新检查已有缺失项和受影响的主题，更新能找到依据的讲解与诊断入口。
- 对话、作答和引用记录保留原有材料版本。若主题内容发生变化，在新对话中使用更新后的依据。
- 仅解析或补传材料时，学生的「待复习」状态取决于已有作答证据。材料覆盖情况显示在课程目录。

### 4. Tutor 教学与诊断

#### 4.1 一次辅导会话

1. 学生选择主题或提交自提题。Tutor 根据当前主题、学生的问题及课件出处建立上下文。
2. Tutor 默认先问学生如何想、从哪一步开始，或为什么使用某个条件。学生可以提交已写出的步骤，也可以描述自己卡在哪里。
3. Tutor 使用学生的回答形成具体假设，例如「学生知道要找两个数，但可能没有把一次项系数和两数之和联系起来」。记录触发判断的作答、推理依据及关联知识点。
4. 根据学生的理解给一个针对性提示，必要时用更简单的例子。通过后续回答缩小诊断范围，让学生有机会说明或纠正自己的思路。
5. 生成一道针对同一概念的新短题。题目需要能区分疑似误解与一次性失误。学生独立提交后，Tutor 根据作答过程判断疑似卡点是否得到支持。

#### 4.2 题型与独立短题

| 题型 | 界面与数据 | 检查办法 |
| --- | --- | --- |
| 选择题 | 显示题干及带 ID 的选项，首版按单选处理 | 核对选项 ID。需要诊断时，为有诊断意义的干扰项记录所对应的误解 |
| 文字填空 | 输入关键词、短句或按题干要求给出简短理由 | 对可枚举的答案核对必要条件及可接受的同义表达。需要判断概念时，依据课件和评分要点核对理由 |
| TeX 填空 | 输入 TeX 并显示公式预览，可包含多个标明顺序的空 | 对支持的数值、分数、基本代数式及条件明确的简单等式，按题目约束核对其数学含义。遇到超出可校验范围或条件不明的作答时，记录待确认及原因 |

- 出题时同时生成题干、对应知识点、预期判断依据和可接受的解法。发布前核对题干与判断依据是否一致。
- 独立作答时展示题干和该题型所需的选项或输入框。提交后再展示提示、参考解法和判断理由。
- 用于确认卡点的选择题需要能区分疑似误解和其他常见错误。学生只选错选项、证据仍有歧义时，保留为「待确认」。
- 短题需针对同一个被怀疑的理解缺口。只要学生提交的证据不足以区分不同原因，就保留为「待确认」。
- 如果学生在独立提交前选择返回讲解，系统保留诊断上下文。下一次独立检查时使用另一道同知识点短题。

#### 4.3 卡点状态

| 状态 | 触发条件 | 下一步 |
| --- | --- | --- |
| 未诊断 | 学生尚无相关作答证据 | 允许开始学习、提问或做诊断题 |
| 待确认 | 学生的作答或解释表露某个疑似卡点 | 给一道无提示短题检验该判断 |
| 待复习 | 独立短题的作答再次暴露**同一个**理解问题 | 加入复习清单，显示卡点及其判断依据 |
| 本次未确认 | 学生在短题中正确运用了相关概念，或结果支持另一种解释 | 保留作答记录。出现另一疑似卡点时，可根据新证据单独确认 |
| 待确认且证据不足 | 答案太短、解法无法可靠判读，或题目未能区分不同原因 | 记录原因，提供补充步骤或重新检查入口 |
| 本轮复习完成 | 已确认卡点经过复习，学生随后独立做对一题并提供足够的关键依据 | 从待复习清单移出该卡点，保留历史证据 |

主题可关联多个卡点。一个主题在仍有已确认、待复习的卡点时显示「待复习」。一次未完成或证据不足的独立检查保留为「待确认」。以上状态描述的是当前复习证据。

数据中以 `pending` 表示待确认，并记录原因，例如尚未作答或证据不足。`review_needed` 对应待复习，`not_confirmed` 对应本次未确认，`resolved` 对应已完成本轮复习。没有相关作答证据的主题显示「未诊断」。

#### 4.4 复习顺序

首次生成目录后，按课件顺序浏览。学生作答后，复习清单先显示含已确认卡点的主题。初稿建议按该主题下尚待复习的卡点数排序，数量相同时沿用课程顺序。进入条目时，应能查看具体卡点、最近相关作答和下一步练习。

#### 4.5 示例

学生解二次方程 $x^2-5x+6=0$，选了 $2$ 和 $3$ 作为两个数，因为乘积为 $6$。Tutor 先问两数之和为什么需要等于 $-5$。如果学生只关注乘积，Tutor 暂时记录「可能没理解一次项系数与两数之和的关系」，必要时用 $x^2+3x+2=(x+1)(x+2)$ 示范。

学生随后独立完成一道同知识点新题。如果其解释再次忽略和的条件，则确认卡点。如果学生能正确选择两个数并说清两个条件，保留本次作答证据，并依据结果更新复习清单。

### 5. 系统设计

#### 5.1 建议技术栈

| 层 | 初稿建议 | 作用 |
| --- | --- | --- |
| 前端 | React、TypeScript、Vite | 组织目录、Tutor 对话、题型组件和处理状态。TeX 预览可用 KaTeX |
| 后端 | Python、FastAPI | 管理课程、文件解析、模型调用和复习状态 |
| PDF 解析 | pypdf | 按页读取文字层 |
| Office 解析与转换（后续） | python-docx、python-pptx、LibreOffice 的无界面转换 | 读取 `.docx`、`.pptx`，在本机转换旧版文件并保留原件与转换结果 |
| 数学核对 | TeX 输入解析与 SymPy | 将首版支持的表达式解析为符号数据，按题目条件比对数值或等价性 |
| 持久化 | SQLite 和本机文件目录 | SQLite 保存应用记录，文件目录保存上传的课件和解析产物 |

构建后的前端和 API 由同一个本机服务提供，默认监听回环地址。开发时可由前端开发服务器代理 API。课件解析和模型调用通过应用任务队列执行，首版可以随本机服务启动一个任务处理进程。 [LibreOffice 命令行参数](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html) · [文档转换格式](https://help.libreoffice.org/latest/en-US/text/shared/guide/convertfilters.html) · [PDF 正文提取](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)

#### 5.2 模块责任

| 模块 | 责任 |
| --- | --- |
| Web 界面 | 显示课程、处理进度、目录、对话、独立短题和复习清单。根据语言偏好加载文案和 Tutor 内容 |
| 课程服务 | 管理课程、材料版本、可用目录和引用定位。每次读取都限定在当前课程及其可访问的材料 |
| 课件处理任务 | 转换旧版文件，提取段落、页或幻灯片内容，识别主题，生成有依据的复习入口，并记录失败阶段 |
| Tutor 服务 | 获取相关课件及作答上下文，生成追问、简例、疑似卡点和短题 |
| 评估与复习服务 | 校验答案和理由，应用卡点状态规则，按已确认卡点生成复习顺序 |
| 模型适配层 | 将所选语言和任务数据传给配置的模型，校验结构化输出，处理超时和失败 |
| 存储 | 保存课件文件、页级片段、版本、对话、短题、作答和状态变更证据 |

#### 5.3 解析、检索和引用

- 为 Word 段落或表格、PDF 页和 PPT 幻灯片生成稳定的内容单元。可识别的标题、正文和公式带上原位置。片段保留所属版本和内容单元序号。
- 从当前课程和对应材料版本检索片段。处理自提题时，使用题目、学生最新解释、当前知识点和必要的相邻课件片段。前置知识补充引用的是能证明**后续用到该知识**的课件位置。
- 模型生成后，服务端核对引文是否来自本轮可引用的材料片段，并检查原文位置能否打开。测试还要由人工核对该位置是否实际支持这句讲解。
- 课件、题目和学生作答作为学习内容进入模型上下文。教学策略、出题规则与状态转换由应用配置和服务端业务规则管理。

#### 5.4 后台处理和失败恢复

1. 文件保存成功后创建材料版本和处理任务。界面显示等待、解析、生成、完成或失败。
2. 同一上传或作答操作使用稳定的请求标识。客户端重发同一个请求时取得已有处理结果。
3. 目录发布前核对任务所用材料版本。课件补传和替换同时发生时，以当前有效的材料版本发布结果。已有可用目录在新内容生成期间仍可查看。
4. 单个文件解析失败时，保留已可用的课件与对话。学生可重试该文件，或上传更清晰的版本。
5. 模型调用失败时，保留学生最后提交的作答。重试以同一作答为基础。只有完整通过校验的结果才能变更复习状态。
6. 生成任务创建时记录 `locale`。如果任务执行期间学生切换语言，原结果保存在对应语言版本下。当前界面只展示与所选语言匹配的 Tutor 内容，作答提交与判定按同一业务 ID 处理。

#### 5.5 教学输出校验

| 输出 | 发布前的检查 |
| --- | --- |
| 知识点目录 | 主题具备材料依据或出现在可确认的原始目录中。缺失项保留缺失标记 |
| 讲解与补讲 | 引用存在且属于当前课程。补讲说明后续应用位置，并标为「前置知识补充」 |
| 疑似卡点 | 能指出具体概念或步骤，以及支持该判断的学生作答。证据不足时继续追问 |
| 无提示短题 | 题目信息完整，能考查疑似卡点，参考答案与题干一致。作答前的页面和接口只发题干与作答所需数据 |
| 诊断结果 | 结果引用学生的具体作答证据，说明其与疑似卡点的关系。服务端按业务规则更新状态 |
| Tutor 输出语言 | 检查输出标记与任务的 `locale` 一致，并检查讲解、题干和反馈的正文。引用原文、专名和公式可按原样保留。语言不符时按生成失败处理，显示所选语言的重试提示 |

#### 5.6 可切换的模型后端

Tutor 和课件分析模块调用同一个模型接口。输入包含任务类型、所需课件片段、相关学生作答、目标 `locale` 和输出结构。模型响应记录 `locale`。输出经过结构校验后，由应用校验引用、判定短题结果和更新复习状态。切换后端后，既有课程和进度仍可使用。

| 模式 | 运行条件 | 调用方式 |
| --- | --- | --- |
| `api` | 本机配置模型接口地址、模型名称及所需认证 | 根据任务调用模型 API，将结果转换为应用约定的数据格式 |
| `codex_cli` | 安装可调用的 Codex CLI，并以有 Codex 使用权限的 ChatGPT 账户登录 | 由本机后端启动 `codex exec`，复用 CLI 原有登录，从最终响应读取应用所需数据 |

API 模式可先实现 OpenAI Responses 接口的适配。生成、追问和评估各自使用明确的输入与输出结构，后续接入其他服务时沿用同一业务接口。 [Responses API 参考](https://developers.openai.com/api/reference/resources/responses/methods/create)

CLI 在本机启动，模型响应由联网服务生成。以 ChatGPT 登录时，用量按该账户的套餐和 Codex 当时适用的额度处理。API 模式按配置的模型服务单独计算用量。 [Codex 登录方式](https://learn.chatgpt.com/docs/auth) · [非交互运行与认证](https://learn.chatgpt.com/docs/non-interactive-mode) · [ChatGPT 套餐与 Codex 用量](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)

##### Codex CLI 接入方式

1. 在设置或启动检查中执行 `codex --version` 和 `codex login status`，确认 CLI 可用且当前认证方式为 ChatGPT。需要登录时，用户在终端运行 `codex login`。编写本文时，本机状态检查已显示 `Logged in using ChatGPT`。
2. 后端用固定的可执行文件和参数列表启动 `codex exec`，通过标准输入 `-` 传入约定的任务数据。使用独立临时目录和 `--skip-git-repo-check` 运行，启用 `--sandbox read-only` 与 `--ephemeral`。应用按本机支持的配置禁用 Shell、插件和搜索，并通过 `--ignore-user-config` 避免载入个人项目工具配置。
3. 用 `--output-schema` 约束最终响应的结构，通过 `--output-last-message` 读取最终输出。应用再次校验结构、来源和业务状态后入库。CLI 认证沿用其本地登录机制，传给 CLI 的环境保持独立于 API 模式的认证配置。
4. 接口处理 CLI 缺失、启动失败、未以 ChatGPT 登录、联网失败、超时、用量受限和结构校验失败。失败时保留原始课件和学生作答，允许在同一任务上重试。用户可在任务空闲时从模型设置切换本次运行的后端。启动默认值从本机环境变量读取。 [Codex CLI 参数](https://learn.chatgpt.com/docs/cli/reference) · [非交互输出格式](https://learn.chatgpt.com/docs/non-interactive-mode)

#### 5.7 本机配置和数据

| 配置项 | 含义 |
| --- | --- |
| `AI_TUTOR_PROVIDER` | 选择 `api` 或 `codex_cli` |
| `AI_TUTOR_DATA_DIR` | SQLite、上传文件和解析产物的位置 |
| `AI_TUTOR_API_BASE_URL`、`AI_TUTOR_API_MODEL`、`AI_TUTOR_API_KEY` | API 模式的服务地址、模型和后端凭证 |
| `AI_TUTOR_CODEX_BIN` | Codex CLI 命令或可执行文件路径 |
| `AI_TUTOR_SOFFICE_BIN`（Office 支持启用后） | LibreOffice 转换程序路径 |

上传文件先在本机解析。课程分析将需要判断的正文按片段发送给选定后端，辅导轮次只发送相关出处和必要的作答上下文。课件原文件、数据库和进度留在本机。模型密钥由本机后端管理。日志记录任务阶段、耗时和错误类别，便于排查上传、解析和生成问题。

启动时检查数据目录可写、所选模型后端的配置可读。旧版 Office 支持启用后，检查转换程序是否可调用。转换程序缺失时，上传 `.doc` 或 `.ppt` 应得到安装或配置提示。浏览器请求通过应用的本机地址访问，保存文件和改写状态前校验请求来源。

### 6. 数据设计

以下为逻辑数据结构。可在实现时按实际数据库和存储方式调整字段类型。

| 实体 | 主要字段 | 用途 |
| --- | --- | --- |
| 本机偏好 | `locale`、更新时间 | 统一控制界面和 Tutor 输出语言 |
| 课程 | ID、名称、创建与更新时间、当前目录版本 | 作为课程材料、对话和复习记录的归属 |
| 材料版本 | ID、课程 ID、文件名、类型、校验值、存储位置、解析状态、上一版本 ID | 追踪补传、替换和引用 |
| 内容单元 | 材料版本 ID、单元序号、段落/表格/页/幻灯片类型、标题、原文片段、原位置信息 | 作为检索和显示引用的基本单位 |
| 知识点 | ID、课程 ID、上级知识点 ID、名称、课程顺序、覆盖状态、出处 | 生成目录。覆盖状态描述材料能否支持该主题 |
| 辅导内容 | 知识点 ID、课程目录版本、内容类别、文本、引用 | 保存短讲解、简例、诊断入口和前置补讲 |
| Tutor 内容语言版本 | 原内容类型与 ID、内容版本、`locale`、展示文本 | 按需保存目录名称、讲解、对话、短题、卡点说明或反馈的语言版本，共用业务 ID、引用和判定数据 |
| 会话与消息 | 课程 ID、会话 ID、主题 ID、消息 ID、发送者、内容、引用、时间 | 回看学生尝试与 Tutor 的引导 |
| 卡点记录 | ID、课程 ID、知识点 ID、具体误解、证据消息、状态、确认作答 ID | 关联疑似卡点、确认依据与复习状态 |
| 短题 | ID、对应卡点或练习主题、题型、题干、选项或填空字段、验证方式、判断依据、出处 | 支持独立检查。判分依据保存在服务端 |
| 作答 | ID、短题 ID、所选选项 ID 或各空的答案、解释、独立作答状态、判断结果、提交时间 | 支持诊断、历史记录和复习完成后的验证 |
| 处理任务 | ID、课程 ID、材料版本 ID、`locale`、阶段、状态、错误原因、请求标识、更新时间 | 支持显示进度、重试和排查问题 |

**一致性规则。** 引用通过「材料版本 ID + 1 起始的内容单元序号」定位。复习清单从仍处于「待复习」的已确认卡点生成。一次提交最多产生一条有效作答结果，保存结果与更新对应卡点状态需要同时完成。旧作答和对话可回看发生时所用的材料版本。

### 7. 接口草案

接口使用 `/api/v1` 前缀。上传文件使用表单请求，其余请求和响应使用 JSON。课程、主题、会话、短题和作答都由服务端分配 ID。

| 方法与路径 | 输入 | 主要返回 |
| --- | --- | --- |
| `GET /preferences` | 无 | 当前 `locale` |
| `PATCH /preferences` | `locale` 为 `zh-Hans` 或 `en` | 保存后的 `locale` |
| `POST /courses` | 课程名称 | 课程 ID |
| `GET /courses` | 可选分页条件 | 可继续复习的课程及其状态 |
| `POST /courses/{courseId}/materials` | 文件、请求标识、可选被替换版本 | 材料版本 ID、处理任务 ID |
| `GET /courses/{courseId}/jobs/{jobId}` | 任务 ID | 当前阶段、状态、错误原因、可执行操作 |
| `POST /courses/{courseId}/jobs/{jobId}/retry` | 请求标识 | 重试任务 ID |
| `GET /courses/{courseId}/topics` | 课程 ID | 目录版本、当前语言的主题树、覆盖状态、复习标记和出处 |
| `POST /courses/{courseId}/localizations` | 需要显示的内容类型、ID 与版本，请求标识 | 当前 `locale` 的缓存内容或生成任务 ID |
| `GET /courses/{courseId}/materials/{versionId}/units/{index}` | 材料版本、内容单元序号 | 原文片段和可打开的位置 |
| `POST /courses/{courseId}/sessions` | 主题 ID 或学生自提题 | 会话 ID、适用目录版本 |
| `GET /courses/{courseId}/sessions` | 课程 ID | 可继续的会话及其主题、最近时间和阶段 |
| `GET /sessions/{sessionId}` | 会话 ID | 对话记录、引用、疑似卡点和进行中的独立短题 ID |
| `POST /sessions/{sessionId}/messages` | 学生文字、公式或步骤、请求标识 | Tutor 追问或讲解、出处、疑似卡点和后续操作 |
| `POST /diagnoses/{diagnosisId}/checks` | 卡点 ID、确认或复习复核、请求标识 | 独立短题 ID、题干、题型、选项或填空字段 |
| `POST /courses/{courseId}/topics/{topicId}/checks` | 知识点 ID、请求标识 | 同知识点的独立练习题 |
| `GET /checks/{checkId}` | 独立短题 ID | 短题状态。作答前返回题干和输入项，作答后可恢复已保存的结果 |
| `POST /checks/{checkId}/attempts` | 选项 ID 或各空的输入、题目要求的关键理由、请求标识 | 作答 ID、判定与依据、卡点新状态及相关知识点 |
| `GET /courses/{courseId}/review` | 课程 ID | 按当前作答证据排序的复习清单 |
| `GET /runtime/status` | 无 | 当前模型后端和本机依赖的就绪状态 |
| `PATCH /runtime/settings` | 后端类型、该后端的模型 ID 和思考强度，以及 API 模式可选的地址和密钥 | 本次运行的后端和两套模型设置。输入的密钥留在服务内存中 |
| `POST /runtime/models` | 后端类型，以及 API 模式可选的地址和密钥 | 该后端返回的可用模型及已有的强度信息 |
| `POST /runtime/model-efforts` | API 模型 ID，可选的地址和密钥 | 从模型详情或输入 token 计数接口获取的思考强度 |

生成类请求按保存的偏好记录 `locale`。接口返回 Tutor 内容时同时返回语言标记。等待生成所选语言的内容时，界面显示对应语言的加载或重试提示。

普通错误响应包含错误代码、文案所需的动态参数和可执行的恢复操作。界面按 `locale` 展示说明。例如文件无法解析时，返回受影响文件并提示如何补传。学生作答证据不足时，返回正常的「待确认」结果和补充步骤入口。

开始独立检查后，题目保持可恢复。每道短题接收一次正式提交，同一请求标识可重取结果。学生重新检查时生成新的短题。对应卡点及作答状态以服务端保存的结果为准。

以下为同一道独立 TeX 短题的简体中文响应。英文响应沿用同一个短题 ID 和填空字段 ID。

```json
{
  "checkId": "check_021",
  "format": "tex",
  "locale": "zh-Hans",
  "prompt": "将 $x^2-7x+12$ 写成 $(x+a)(x+b)$ 的形式，并按从小到大的顺序填入 $a$ 和 $b$。",
  "fields": [
    { "id": "a", "label": "较小的数 a" },
    { "id": "b", "label": "较大的数 b" }
  ]
}
```

### 8. 测试与验收

#### 8.1 功能验收用例

| 用例 | 操作 | 通过条件 |
| --- | --- | --- |
| PDF 导入 | 上传第 8.3 节的英文假设检验课件 | 生成目录与辅导入口，重复出现的目录页合并。可用主题能跳到对应 PDF 物理页 |
| 图片正文缺失 | 上传同时包含可读正文和扫描页或截图页的课件 | 可读部分能继续使用。不可读取的单元标出位置并提供补传提示 |
| 已知主题缺材料 | 上传带目录、缺一章正文的课件 | 目录保留该章，显示「材料缺失」及补传入口。补传成功后更新受影响内容 |
| 前置知识补讲 | 课件正文跳过已知后续推导所用的前置概念 | 显示简短前置补讲及其后续应用位置。涉及的原文和补讲显示各自依据 |
| 两类材料依据都缺 | 上传缺目录、仅包含数个已知章节的课件 | 目录展示可确认的主题。针对已知内容用到的前置知识应用补讲规则 |
| 自提新题和追问 | 输入课件中未预设的一道新题并给出一步作答 | Tutor 从学生已有步骤出发，先追问理由，再按需要给提示或简例 |
| 无提示检查确认 | 提交一道短题，并在作答中复现原先疑似的误解 | 提交前页面与响应只提供作答所需内容。提交后显示判断依据，并将该卡点列入「待复习」 |
| 短题出现另一原因 | 题目作答展示不同错误或证据含糊 | 原疑似卡点保留「待确认」或「本次未确认」。新的疑似卡点按其自身证据处理 |
| 独立做对 | 引导后完成与疑似卡点相关的短题，并说清关键条件 | 记录本次作答。未确认的疑似卡点按规则关闭，已确认卡点在通过复习验证后从清单中移除 |
| 三类作答 | 分别完成一道选择题、文字填空和 TeX 填空 | 选项 ID、文本和公式可正确保存与校验。等价的受支持公式可通过同一题目校验 |
| 本机记录恢复 | 完成一轮辅导，刷新页面并重启服务 | 课件、对话、短题作答和复习顺序仍可恢复 |
| 两种模型后端 | 分别配置模型 API 和 ChatGPT 登录的 Codex CLI，跑同一套最小流程 | 两种模式返回同一业务结构，并能生成带有效出处的辅导和短题。模拟超时或结构错误时保留已提交作答 |
| 界面和 Tutor 同语 | 分别选择简体中文和 English。使用同一份英文课件，用中文提问、用英文作答并触发文件错误 | 界面文案、目录、Tutor 讲解、题目和反馈均跟随所选语言。引用保持原文，文件错误按界面语言显示 |
| 复习中切换语言 | 输入一部分短题答案，在 Tutor 生成中或查看旧会话时切换语言，然后重启应用 | 界面只展示所选语言的 Tutor 内容。短题 ID、已输入的答案、判定和进度保留。重启后语言选择仍有效 |
| 恢复与重试 | 重复发送同一请求，模拟一次解析或模型调用失败 | 保留已有课件和作答，一次操作只产生一条有效结果，界面可发起受影响步骤的重试 |

#### 8.2 试用指标

| 指标 | 记录方式 |
| --- | --- |
| 找到复习内容的用时 | 从打开课程起，到学生找到一个经题目或人工反馈确认需要复习的知识点 |
| 卡点定位准确率 | 由助教阅读同样的作答、解释和短题，独立判断是否存在该卡点。计算已确认卡点中与助教判断一致的比例，同时记录漏判和仍待确认的数量 |
| 课程引用正确性 | 核对引用能否打开，以及该页或幻灯片是否支持实际给出的解释 |
| 独立练习表现 | 记录学生在关闭提示的情况下能否完成同知识点新题，以及其关键理由是否正确 |
| 处理稳定性 | 记录材料解析与内容生成成功率、失败阶段、重试次数和等待时间 |

试用可以选择 Gemini 学习笔记本或 StudyFetch 作为对照。在相同课件、复习任务和时长下，观察找到复习内容的速度和卡点判断的准确性。先记录小规模试用的基线，再确定后续版本的指标阈值。 [Gemini 学习笔记本](https://blog.google/innovation-and-ai/products/gemini-app/gemini-study-notebooks/) · [StudyFetch](https://www.studyfetch.com/support)

#### 8.3 第一批验收样例

首批验收使用学生提供的本机课件 `7. Hypothesis Testing.pdf`（UFUG2104 Applied Statistics，125 页）。以下页码按上传文件的物理页从 1 开始计数。作答案例是为验收编写的。真实学生作答和试用指标仍需在试用时收集。

| 预期目录 | 可检查的课件出处 |
| --- | --- |
| 假设检验概念 | 第 16 页未拒绝的含义，第 32 页两类错误，第 38–39 页 p 值，第 40–42 页单双侧拒绝域，第 49 页检验力 |
| 正态情形下的假设检验 | 第 58–81 页总体均值检验（第 81 页比较 z 检验与 t 检验），第 98–102 页总体方差检验 |
| 双总体假设检验与 A/B 测试 | 第 115 页双总体均值，第 118 页双总体比例 |

第 2、3、55、112 页的目录只生成一套主题树。点击表中任一出处应打开对应页。用 pypdf 读取第 125 页可得到标题和页码。Tutor 根据提取到的文字引用该页，页面中的代码不能作为文字证据。

| 作答方式 | 可重复的验收场景与预期 |
| --- | --- |
| 文字填空与卡点诊断 | 学生说「p 大于 0.05，所以原假设成立」。Tutor 先追问理由，并用第 16、38–39 页建立疑似卡点。另出一道网页转化率测试题，给定 p = 0.08、α = 0.05，要求判断并说明结论。再次说「证明原假设成立」时列入「待复习」。只写「不显著」时保留「待确认」。回答「证据不足以拒绝，仍不能判断原假设为真」时记为「本次未确认」。对于已确认的卡点，再换一道同概念新题（如 p = 0.03、α = 0.01），答对并说明同一关键理由后移出待复习清单。 |
| 单选 | 给出新情境，说明总体实际满足原假设，而检验拒绝了原假设。选择「第一类错误」应判对，依据第 32 页。 |
| TeX 填空 | 给定某具体备择条件下的第二类错误概率为 0.2，要求输入检验力。依据第 49 页，`0.8`、`\frac{4}{5}` 和 `1-0.2` 均判对，`0.2` 判错。 |

需要测试扫描页时，可从原件制作两页 PDF，保留原第 124 页的文字层，把原第 125 页转成纯图片。副本第 1 页应可用，第 2 页应提示正文不可读取。测试材料缺失时，先上传原第 1–111 页（保留目录），再补传第 112–125 页。补传前 A/B 测试显示「材料缺失」，补传后可引用补传文件第 4、7 页。

先用固定模型输出验证页面、状态规则、双语切换和重启恢复，再用两种真实模型后端分别跑同一条主流程。

### 9. 建议开发顺序

1. **本机骨架与测试样例。** 搭建课程页、双语文案和语言设置、SQLite 及数据目录，使用第 8.3 节的 PDF 课件和预期结果。
2. **课件导入与目录。** 完成 PDF 解析、原文定位、不可读页提示、材料缺失和补传。用一套固定模型输出验证课程状态。
3. **Tutor 和复习清单。** 实现自提问题、按学生思路追问、三种答题方式、独立短题，以及有作答证据的状态转换。验证应用重启后可继续复习。
4. **模型接入与联调。** 接入 API 和 Codex CLI，验证两条生成链路使用相同的输出结构、语言设置、引用校验和失败恢复规则。
5. **用真实材料验收。** 跑通假设检验课件的主流程。试用时记录找复习内容的用时、卡点判断一致性、出处准确性与生成耗时，并据结果确定量化目标。

### 10. 需求依据

- 项目问卷汇总和四次看图访谈支持复习方向、具体卡点反馈及课件一致性的需求。 [问卷汇总](C:/Users/Asbab/Downloads/surveyfull.docx) · [访谈记录](<C:/Users/Asbab/Downloads/interview transcript.docx>)
- 项目市场调研记录了校内物理预设题系统和公式输入方式。首版以本人课件生成跨学科 Tutor，并接收学生自行提出的问题。 [市场调研报告](<C:/Users/Asbab/Downloads/AI Tutor Market Research Report.pptx>)

<a name="en"></a>

## English

Version 0.1 · Development draft

AI Tutor helps students prepare for exams using their own course materials. After a student uploads materials, the system analyzes them and generates a topic outline, explanations, worked examples, and practice. Students can start from the outline or ask their own questions. The Tutor asks how the student is thinking, uses one short check without hints to confirm a possible gap, and updates that student's review order.

The project has user research and an interface screenshot with demonstration data. The screenshot illustrates the interaction. Validate product behavior using real materials and student answers.

### 1. Product goals and MVP scope

#### 1.1 MVP deliverables

- **Delivery** is a single-user Web app that runs on the student's computer. The full workflow runs with real course materials. Saved progress survives a page refresh and a service restart.
- **Current file format** is `.pdf`. Use extractable text, mark scanned or screenshot-only pages, and prompt the student to upload readable material. Word and PowerPoint support is deferred to a later iteration.
- **Languages** include Simplified Chinese and English for the interface. One language setting controls interface copy and Tutor output. Materials, questions, and student answers can use other languages or mix languages.
- **Answer formats** are multiple-choice questions, text blanks, and TeX blanks. The API draft starts with single-answer choice questions. The Tutor chat also accepts text so students can ask questions and describe their reasoning.
- **Data and model access** use local storage for materials, outlines, conversations, answers, and progress. The model backend can use an online API or the local Codex CLI signed in with ChatGPT. Each task sends the course excerpts and student work it needs.

#### 1.2 Student tasks

| Student task | MVP outcome | Research evidence |
| --- | --- | --- |
| See what the course covers and decide where to start | Generate an outline that links to source material. After the student answers questions, prioritize topics with confirmed gaps | 22 of 31 survey respondents reported too many topics. Three of four interviewees used homework performance to prioritize review |
| Identify the concept or step they do not understand | Use the student's steps and reasoning to form a hypothesis, then check it with one short question without hints | 22 of 32 respondents had encountered AI that misunderstood their question. 28 of 32 wanted AI to identify the specific step or concept they had missed |
| Check whether an explanation agrees with the materials | Provide a source link for explanations and label material gaps and prerequisite explanations | 21 of 32 respondents had encountered AI explanations that differed from their textbook. One interviewee wanted help filling knowledge gaps |

The survey and walkthrough interviews support these requirements. A pilot should measure how long it takes students to find what to review and how accurately the Tutor identifies gaps. One student can complete the workflow with their own materials and answers.

The system organizes tutoring by course content and answer type. Equation transformations, concept explanations, and explanations of program behavior can use different checks and follow the same workflow for upload, topic generation, guided questions, independent checks, and review ordering.

### 2. Terms and interface

| Term | Definition |
| --- | --- |
| Course | A student's personal review space containing materials, the generated Tutor, conversations, and review records |
| Original outline | A chapter outline or syllabus that can be verified in the materials |
| Review outline | Topic navigation generated from the available material and any verifiable original outline |
| Source reference | A reference to a particular material version and PDF page, slide number, or Word paragraph location |
| Missing material | A topic is listed in a verifiable outline and its main text is unavailable in the uploaded materials |
| Prerequisite explanation | A short explanation of knowledge required by known later material that the uploaded files leave unexplained, with a link to where it is used |
| Possible gap | A hypothesis drawn from the student's answer or explanation that still needs checking |
| Confirmed gap | The student shows the same misunderstanding on an independent check, with evidence in their answer |

#### 2.1 Screens and main actions

| Area | Student action | Interface response |
| --- | --- | --- |
| Course home | Create a course, upload materials, or add missing files | Show upload, parsing, and generation progress, with recovery options after a failure |
| Topic outline | Choose a topic, open a source, or inspect a missing item | Show the topic structure, references, and review status |
| Tutor | Submit an attempt, explain a reason, or ask a new question | Show a follow-up question, a hint if needed, and relevant source material |
| Independent check | Complete one question using its options or input fields | Show the result, reasoning, and related topic after submission |
| Review list | Open a priority topic and inspect the evidence | Show confirmed gaps, relevant recent answers, and a way to practice again |
| Language setting | Choose Simplified Chinese or English | Use the same language for the interface and the Tutor content in view, and restore the choice when the app reopens |

See the [AI Tutor interface screenshot](ai-tutor-screenshot.png) for the layout. Its course materials, page numbers, and dialogue are demonstration data. The MVP answer area provides options, text fields, and TeX input with a preview.

#### 2.2 Interface and Tutor language

- Persist one application preference named `locale`. Support `zh-Hans` and `en`, with Simplified Chinese as the first-run default. The student can switch from the global [language setting](#ui-copy).
- Provide interface buttons, navigation, status messages, and errors in both languages. Generate topic names, explanations, follow-up questions, question stems, options, feedback, and gap descriptions using the same `locale`. Course materials and student input can be in other languages.
- Update interface copy when the student switches languages. Load or generate the selected language version of Tutor content in the current course and conversation on demand, and cache it for later use. Show loading feedback in the selected language until the text is ready. Preserve original quotations, TeX, student answers, and review records.
- Use the same IDs for topics, gaps, checks, options, blanks, and attempts in both languages. Keep question meaning, correct answers, entered answers, results, and progress intact when switching. A question can preserve original wording or terminology when it is part of the material being assessed.

### 3. Generating a Tutor from course materials

#### 3.1 Import and analysis

1. The student creates or opens a course and uploads one or more files. The app displays each filename and processing status.
2. The system extracts readable text and structure by paragraph, page, or slide. It preserves chapters, definitions, examples, readable formulas, and source locations. It also records where text could not be read so the student can supply a clearer version.
3. Use a verifiable table of contents or syllabus when available. The system can also infer topics from readable text. Inferred topics enter the review outline with source references and follow the course order where possible.
4. Generate a starting point for each supported topic, with a learning objective, a short explanation or worked example, and a diagnostic question the student can begin. Missing topics link to file upload.
5. Validate source locations before publishing the Tutor content. Students can start studying supported topics while failed files display their status and a retry option.

#### 3.2 Formats, language, and source locations

| File | Handling | Citation location |
| --- | --- | --- |
| `.pdf` | Extract text by physical page locally | Physical page number starting at 1 |

For later iterations, handle Office formats as follows.

| File | Handling | Citation location |
| --- | --- | --- |
| `.docx` | Read headings, paragraphs, and readable tables locally | Heading path and paragraph or table number |
| `.doc` | Convert locally to `.docx` and retain the original and converted files | Original filename and the heading and paragraph position in the converted document |
| `.pptx` | Read titles, text boxes, and readable tables by slide | Slide number |
| `.ppt` | Convert locally to `.pptx` and record the conversion status | Original filename and slide number after conversion |

Store text in Unicode and preserve original wording, technical terms, and mathematical symbols. A course can mix languages. Tutor explanations follow the language selected in the app. Citations show the original text.

Show the location and the message “Text unavailable” for scanned or screenshot-only PDF pages and pages that could not be parsed. The Tutor can generate content for readable pages. If the file has no usable text, prompt the student to upload a readable file or the relevant pages before generating content.

#### 3.3 Material gaps

| Available evidence | Tutor behavior | What the student sees |
| --- | --- | --- |
| Enough readable course text | Generate tutoring grounded in the relevant page or slide | A reference that opens the original source |
| The original outline lists the topic, and its body text is missing | Keep the topic and prompt the student to upload the relevant material | “Missing material,” the topic name, and a way to upload |
| The material and original outline for a section are unavailable | Continue generating the outline and tutoring from known materials | Topics supported by the available files |
| Known later material requires an unexplained prerequisite | Identify the dependency from a later question or derivation and explain enough of the prerequisite for the student to continue | “Prerequisite explanation,” the gap in the materials, and a link to the later application |
| The file contains no readable material | Keep its processing status and prompt the student to add a readable file or page | The affected file and recovery action |

For example, a handout may go straight from $(x-2)(x-3)=0$ to the two roots without explaining the step. The Tutor explains the zero-product property and links it to the page where it is used. That citation identifies the application. The added explanation is labeled as a prerequisite.

A student can ask a new question that the materials did not specify. The Tutor builds its response from the question, the student's work, and related course materials. If the connection to the course is unclear, the Tutor first asks which topic is relevant or requests supporting material.

#### 3.4 Additional materials and updates

- After successfully parsing new materials, revisit known gaps and affected topics. Update explanations and diagnostic starting points where the new material provides evidence.
- Keep the material versions referenced by existing conversations, answers, and citations. Use the updated version for new conversations when topic content changes.
- Derive the student's review status from answer evidence when material is parsed or added. Show material coverage separately in the outline.

### 4. Tutoring and diagnosis

#### 4.1 A tutoring session

1. The student selects a topic or asks a new question. The Tutor uses that topic, the question, and course sources as context.
2. The Tutor first asks how the student is thinking, which step they would take, or why a condition applies. The student can provide a step they have written or describe where they got stuck.
3. Form a specific hypothesis from the answer. For example, the student knows they must choose two numbers and may have missed the relationship between their sum and the linear coefficient. Record the triggering answer, the rationale, and the topic.
4. Give a targeted hint and use a simpler example as needed. Follow-up dialogue narrows the possible causes and gives the student a chance to explain or revise their reasoning.
5. Generate one new short question that tests the same concept and distinguishes the possible misunderstanding from a one-off mistake. After the student answers independently, judge whether the steps support the hypothesis.

#### 4.2 Question formats and independent checks

| Format | Interface and data | Evaluation |
| --- | --- | --- |
| Choice | Display a question and options with IDs. The MVP accepts a single selected option | Check the option ID. For diagnosis, associate meaningful distractors with the misunderstanding they reveal |
| Text blank | Accept a keyword, short phrase, or brief reason when requested | Check required elements and accepted synonyms for enumerable answers. Use the materials and grading criteria for concept explanations |
| TeX blank | Accept TeX and show a formula preview. A question can have several labeled blanks in a defined order | Compare supported numbers, fractions, basic expressions, and simple equations under the question's stated conditions. Flag answers for confirmation when a form or condition cannot be checked reliably |

- Generate the question, related topic, grading criteria, and accepted approaches together. Check that the question and criteria agree before publishing.
- During independent work, show the question and the options or fields it requires. Show hints, sample solutions, and the reason for the result after submission.
- A diagnostic choice question must distinguish the suspected gap from other common errors. Keep the status at “Awaiting confirmation” when a wrong choice alone leaves the cause ambiguous.
- The short question must test the same suspected gap. Keep it awaiting confirmation if the submitted evidence cannot distinguish the causes.
- If the student returns to tutoring before submitting, preserve the diagnosis context. Use a different question on the same topic for the next independent check.

#### 4.3 Gap and review statuses

| Status | Trigger | Next action |
| --- | --- | --- |
| Not assessed | The student has no relevant answer evidence | Start studying, ask a question, or take a diagnostic check |
| Awaiting confirmation | The student's work suggests a possible gap | Test the hypothesis with one short question without hints |
| Needs review | The independent answer shows the **same** misunderstanding | Add the gap to the review list and show the supporting evidence |
| Not confirmed | The student correctly applies the concept, or the answer supports another cause | Keep the answer history. Investigate another possible gap from its own evidence |
| Awaiting confirmation due to insufficient evidence | The answer is too short, its reasoning cannot be read reliably, or the question does not distinguish the causes | Record why and offer a way to add steps or check again |
| Review complete | After reviewing a confirmed gap, the student solves a new question independently and provides the key reasoning | Remove that gap from the current review list and keep the evidence |

A topic can have several gaps. It displays “Needs review” while it has any confirmed gap awaiting review. An unfinished check or one with insufficient evidence keeps its “Awaiting confirmation” status. The status reflects current review evidence.

In storage, `pending` means awaiting confirmation and records a reason such as an unanswered check or insufficient evidence. `review_needed` means needs review, `not_confirmed` means not confirmed, and `resolved` means review complete for this round. A topic with no relevant answer evidence displays “Not assessed.”

#### 4.4 Review order

Show the generated outline in course order on first use. After the student answers, put topics with confirmed gaps first. The draft orders topics by the number of confirmed gaps still needing review, with course order breaking ties. Students can open a topic to see the specific gap, related recent answers, and the next practice item.

#### 4.5 Example

A student solving $x^2-5x+6=0$ chooses $2$ and $3$ because their product is $6$. The Tutor first asks why the sum must be $-5$. If the student considers only the product, the Tutor records a possible gap in relating the linear coefficient to the sum and can demonstrate $x^2+3x+2=(x+1)(x+2)$.

The student then answers a new question on the same concept independently. If their explanation again overlooks the sum, the Tutor confirms the gap. If the student chooses the correct numbers and explains both conditions, save the evidence and update the review list accordingly.

### 5. System design

#### 5.1 Proposed technology stack

| Layer | Draft recommendation | Purpose |
| --- | --- | --- |
| Frontend | React, TypeScript, Vite | Organize the outline, Tutor chat, question components, and processing feedback. KaTeX can render TeX previews |
| Backend | Python, FastAPI | Manage courses, file parsing, model calls, and review status |
| PDF parsing | pypdf | Read the text layer by page |
| Office parsing and conversion (later) | python-docx, python-pptx, headless LibreOffice | Read `.docx` and `.pptx`, convert legacy files locally, and retain originals and converted files |
| Math validation | TeX parsing and SymPy | Parse supported expressions into symbolic data and check values or equivalence under the problem's stated conditions |
| Persistence | SQLite and a local file directory | Store application records in SQLite and keep uploaded files and parsing results in the file directory |

Serve the production frontend and API from the same local service, which binds to the loopback interface by default. In development, the frontend development server can proxy API requests. File processing and model calls use an application job queue. The MVP can start one worker with the local service. [LibreOffice command-line parameters](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html) · [Conversion filters](https://help.libreoffice.org/latest/en-US/text/shared/guide/convertfilters.html) · [PDF text extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)

#### 5.2 Module responsibilities

| Module | Responsibility |
| --- | --- |
| Web interface | Show courses, processing progress, topics, conversations, independent checks, and review lists. Load interface copy and Tutor content for the selected language |
| Course service | Manage courses, material versions, available outlines, and source locations. Limit reads to the current course and its available files |
| File processing jobs | Convert legacy formats, extract paragraphs, pages, and slides, identify topics, generate grounded starting points, and record the stage of any failure |
| Tutor service | Retrieve relevant source and answer context. Generate follow-up questions, worked examples, possible gaps, and short questions |
| Evaluation and review service | Check answers and reasons, apply status transition rules, and order review topics using confirmed gaps |
| Model adapter | Send the selected language and task data to the configured model. Validate structured results and handle timeouts and failures |
| Storage | Keep uploaded files, source excerpts, versions, conversations, questions, answers, and evidence of status changes |

#### 5.3 Parsing, retrieval, and citations

- Assign stable content units to Word paragraphs and tables, PDF pages, and PowerPoint slides. Keep locations for readable headings, text, and formulas. Each excerpt retains its material version and unit number.
- Retrieve excerpts from the current course and the relevant material versions. For student questions, use the question, latest explanation, current topic, and adjacent source excerpts as needed. A prerequisite explanation cites the location that shows **where the knowledge is used later**.
- After generation, check that references come from permitted excerpts for that task and open to the right source location. During testing, also have reviewers check whether the cited passage supports the explanation.
- Provide materials, questions, and student answers to the model as learning content. Application configuration and backend rules define the teaching strategy, question rules, and status transitions.

#### 5.4 Background jobs and recovery

1. Save a material version and create a job after storing the file. Show queued, parsing, generating, complete, or failed status.
2. Give each upload or answer operation a stable request ID. Resubmitting the same request returns the existing result.
3. Check the input versions before publishing the outline. If uploads and replacements overlap, publish the result for the current versions. Students can continue using an existing outline while new content is generated.
4. Keep available materials and conversations when a file fails to parse. The student can retry that file or upload a clearer version.
5. Keep the latest submitted answer if a model call fails. Retry using the same answer. Update review status after the result passes all required checks.
6. Capture the `locale` when creating a generation job. If the student switches languages while it runs, save the result under its original locale. Display Tutor content for the active language and use the same business IDs for answer submission and evaluation.

#### 5.5 Tutor output validation

| Output | Check before publishing |
| --- | --- |
| Topic outline | Each topic has source evidence or appears in a verifiable original outline. Keep missing-material labels for uncovered topics |
| Explanations and prerequisite notes | References exist and belong to the current course. Prerequisite notes indicate the later application and carry the “Prerequisite explanation” label |
| Possible gap | Identify the particular concept or step and the student work that suggests the gap. Ask another question when evidence is insufficient |
| Independent check | The question is complete, tests the suspected gap, and agrees with its reference answer. Before submission, expose the question and only the data needed to answer |
| Diagnosis result | Cite the student's specific answer evidence and explain its relationship to the suspected gap. Apply status changes through backend rules |
| Tutor output language | Check the output language marker against the job's `locale` and check the language of the explanation, question, and feedback. Preserve quotations, proper names, and formulas where needed. Treat a language mismatch as a generation failure and show a retry message in the selected language |

#### 5.6 Switchable model backends

The Tutor and course analysis modules use one model interface. Its inputs include a task type, the necessary course excerpts and student work, the target `locale`, and an output schema. The model response records its `locale`. After validating the response structure, the application checks citations, evaluates short answers, and updates review status. Courses and progress remain available across backend switches.

| Mode | Requirements | Invocation |
| --- | --- | --- |
| `api` | A configured model endpoint, model name, and required credentials on the local computer | Call the model API for the task and normalize its response to the application schema |
| `codex_cli` | A callable Codex CLI signed in to a ChatGPT account with Codex access | Start `codex exec` on the local backend, reuse the CLI's stored login, and read the final structured output |

The initial API adapter can use the OpenAI Responses format. Generation, follow-up questions, and evaluation each have defined inputs and outputs. Other providers can use the same application interface through their adapters. [Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create)

The CLI runs locally and receives model responses from an online service. A ChatGPT sign-in uses the account's applicable plan and Codex limits. API mode uses the configured model service's own usage rules. [Codex authentication](https://learn.chatgpt.com/docs/auth) · [Non-interactive mode and authentication](https://learn.chatgpt.com/docs/non-interactive-mode) · [ChatGPT plans and Codex usage](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)

##### Codex CLI integration

1. Run `codex --version` and `codex login status` in the settings or startup check to confirm that the CLI is available and uses ChatGPT authentication. A user who needs to sign in can run `codex login` in a terminal. On the reference computer, the check reported `Logged in using ChatGPT` when this draft was written.
2. Start `codex exec` using a fixed executable and argument list, and pass the task data on standard input with `-`. Run it in a dedicated temporary directory with `--skip-git-repo-check`, `--sandbox read-only`, and `--ephemeral`. Disable shell, plugin, and search tools using supported local settings, and use `--ignore-user-config` to avoid loading tools from personal configuration.
3. Use `--output-schema` to constrain the final response and `--output-last-message` to read it. Validate the structure, citations, and business status before saving. Let the CLI manage its own login and keep API-mode credentials out of the CLI process environment.
4. Handle a missing CLI, launch errors, a missing ChatGPT sign-in, connectivity problems, timeouts, usage limits, and invalid response schemas. Keep materials and submitted answers so the student can retry the same task. The user can switch backends for the current run from Model settings while jobs are idle. The service reads startup defaults from local environment variables. [Codex CLI options](https://learn.chatgpt.com/docs/cli/reference) · [Non-interactive output](https://learn.chatgpt.com/docs/non-interactive-mode)

#### 5.7 Local configuration and data

| Setting | Meaning |
| --- | --- |
| `AI_TUTOR_PROVIDER` | Select `api` or `codex_cli` |
| `AI_TUTOR_DATA_DIR` | Location of SQLite, uploads, and parsing results |
| `AI_TUTOR_API_BASE_URL`, `AI_TUTOR_API_MODEL`, `AI_TUTOR_API_KEY` | API service endpoint, model, and backend credentials |
| `AI_TUTOR_CODEX_BIN` | Codex CLI command or executable path |
| `AI_TUTOR_SOFFICE_BIN` (once Office support is enabled) | LibreOffice conversion executable path |

Parse uploaded files locally first. Course analysis sends the excerpts needed for each analysis job to the selected backend. Tutoring requests send relevant sources and the necessary answer context. Keep original files, the database, and review progress on the computer. Manage model credentials on the local backend. Log job stages, durations, and error categories to diagnose upload, parsing, and generation issues.

At startup, check that the data directory is writable and the chosen model configuration is readable. Once legacy Office support is enabled, check that the converter is available. If it is missing, uploading `.doc` or `.ppt` should show an installation or configuration prompt. Browser requests use the application's local address. Check the request origin before saving files or changing state.

### 6. Data design

The tables describe the logical data model. Field types can follow the database and storage design chosen for implementation.

| Entity | Main fields | Purpose |
| --- | --- | --- |
| Local preference | `locale`, updated time | Set the language for both the interface and Tutor output |
| Course | ID, name, created and updated times, current outline version | Own materials, conversations, and review history |
| Material version | ID, course ID, filename, format, checksum, storage path, parsing status, previous version ID | Track uploads, replacements, and references |
| Content unit | Material version ID, unit number, type, heading, excerpt, source location | Retrieve and display references to paragraphs, tables, pages, or slides |
| Topic | ID, course ID, parent ID, name, course order, coverage status, references | Generate the outline and record whether uploaded materials support the topic |
| Tutor content | Topic ID, outline version, content type, text, references | Store short explanations, worked examples, diagnostic starting points, and prerequisite explanations |
| Tutor content language variant | Content type and ID, content revision, `locale`, display text | Store localized topic names, explanations, dialogue, questions, gap descriptions, or feedback as needed while sharing business IDs, sources, and grading data |
| Session and message | Course ID, session ID, topic ID, message ID, author, content, references, timestamp | Reopen student work and Tutor guidance |
| Gap record | ID, course ID, topic ID, specific misunderstanding, evidence messages, status, confirmation attempt ID | Link the hypothesis, evidence, and review status |
| Check question | ID, gap or practice topic, question format, prompt, options or blanks, validation method, grading criteria, references | Support an independent check. Keep grading criteria on the backend |
| Attempt | ID, check ID, selected option ID or blank values, explanation, independent attempt status, evaluation, submitted time | Support diagnosis, answer history, and review verification |
| Job | ID, course ID, material version ID, `locale`, stage, status, error, request ID, updated time | Show progress, retry, and diagnose failures |

**Consistency rules.** Resolve references using a material version ID and a one-based content unit number. Derive the review list from confirmed gaps that need review. Each submission creates at most one valid result. Save that result and update the gap status together. Keep access to the material versions used for past answers and conversations.

### 7. API draft

Use the `/api/v1` prefix. Upload files as form requests and use JSON for other requests and responses. The server assigns IDs for courses, topics, sessions, checks, and attempts.

| Method and path | Input | Main result |
| --- | --- | --- |
| `GET /preferences` | None | Current `locale` |
| `PATCH /preferences` | `locale` of `zh-Hans` or `en` | Saved `locale` |
| `POST /courses` | Course name | Course ID |
| `GET /courses` | Optional pagination | Courses that can be reopened and their status |
| `POST /courses/{courseId}/materials` | File, request ID, optional version to replace | Material version ID and job ID |
| `GET /courses/{courseId}/jobs/{jobId}` | Job ID | Current stage, status, error, and recovery options |
| `POST /courses/{courseId}/jobs/{jobId}/retry` | Request ID | Retry job ID |
| `GET /courses/{courseId}/topics` | Course ID | Outline version, topic tree in the active language, coverage, review status, and sources |
| `POST /courses/{courseId}/localizations` | Content type, ID, and revision to display, request ID | Cached content or generation job ID for the current `locale` |
| `GET /courses/{courseId}/materials/{versionId}/units/{index}` | Material version and unit number | Original excerpt and source location |
| `POST /courses/{courseId}/sessions` | Topic ID or a student question | Session ID and applicable outline version |
| `GET /courses/{courseId}/sessions` | Course ID | Sessions that can be resumed, with topic, timestamp, and stage |
| `GET /sessions/{sessionId}` | Session ID | Conversation, references, possible gaps, and open independent check ID |
| `POST /sessions/{sessionId}/messages` | Student text, formula or steps, request ID | Follow-up or explanation, references, possible gap, and next action |
| `POST /diagnoses/{diagnosisId}/checks` | Gap ID, confirmation or review check, request ID | Independent check ID, prompt, format, and options or fields |
| `POST /courses/{courseId}/topics/{topicId}/checks` | Topic ID, request ID | Independent practice on the topic |
| `GET /checks/{checkId}` | Independent check ID | Check status. Return the question and input fields before submission, or restore the saved result afterward |
| `POST /checks/{checkId}/attempts` | Selected option ID or blank values, any required reason, request ID | Attempt ID, result and evidence, new gap status, and topic |
| `GET /courses/{courseId}/review` | Course ID | Review list ordered by current answer evidence |
| `GET /runtime/status` | None | Active model backend and local dependency status |
| `PATCH /runtime/settings` | Backend type, its model ID and reasoning effort, and optional API URL and key | Active backend for this run and both sets of model settings. Entered keys stay in service memory |
| `POST /runtime/models` | Backend type and optional API URL and key | The backend's available models and any advertised reasoning levels |
| `POST /runtime/model-efforts` | API model ID and optional API URL and key | Reasoning levels from model details or input token counting |

A generation request captures the saved `locale`. Tutor content responses include a language marker. Show loading or retry copy in the active language while Tutor content for that language is being generated.

Ordinary error responses carry a code, message parameters, and available recovery actions. The interface displays the explanation using `locale`. For a parsing problem, for example, identify the affected file and show how to upload more material. Insufficient answer evidence returns the ordinary “Awaiting confirmation” status and an action to add steps.

Keep open checks resumable. Each question accepts one final submission, and the same request ID can retrieve the result again. Generate a new question for another check. The server's saved result controls the attempt and gap status.

The response below is the English version of the same independent TeX check. The Simplified Chinese version uses the same check ID and field IDs.

```json
{
  "checkId": "check_021",
  "format": "tex",
  "locale": "en",
  "prompt": "Write $x^2-7x+12$ in the form $(x+a)(x+b)$. Enter $a$ and $b$ in ascending order.",
  "fields": [
    { "id": "a", "label": "Smaller value a" },
    { "id": "b", "label": "Larger value b" }
  ]
}
```

### 8. Testing and acceptance

#### 8.1 Functional acceptance cases

| Case | Action | Pass condition |
| --- | --- | --- |
| PDF import | Upload the English hypothesis testing course material from section 8.3 | Generate an outline and Tutor starting points. Merge repeated agenda pages and open supported topics at the correct physical pages |
| Text unavailable in images | Upload materials with readable text and scanned or screenshot-only pages | Keep readable content usable. Show the affected locations and a prompt to supply readable text |
| Known topic with missing material | Upload materials with an outline and a missing chapter | Keep the chapter and show “Missing material” with an upload action. Update affected content after the student uploads it |
| Prerequisite explanation | Use course text that skips a prerequisite required by a known later derivation | Explain the prerequisite briefly and point to its later application. Show the source text and the basis for the added explanation |
| Unavailable material and outline | Upload materials that have no outline and contain several known chapters | Show supported topics and explain prerequisites needed by the known material |
| Student question and follow-up | Ask a question not predefined in the source and submit one step | Start from the student's step and ask why they took it. Offer a prompt or example if needed |
| Confirmation without hints | Take a short check and repeat the suspected misunderstanding | Before submission, show and return only the data needed to answer. Afterward, show the evidence and mark the gap “Needs review” |
| Another cause on the short check | Submit an answer that shows another error or leaves the evidence ambiguous | Keep the original hypothesis “Awaiting confirmation” or “Not confirmed.” Evaluate a new hypothesis using its own evidence |
| Correct independent answer | After tutoring, complete a relevant short check and explain its key conditions | Save the attempt. Close an unconfirmed hypothesis under the prescribed rules. Remove a confirmed gap from the review list once the student passes its review check |
| Three answer formats | Complete one choice, text blank, and TeX blank question | Save and validate the chosen ID, text, or formula. Supported equivalent formulas pass the same check |
| Restore local records | Complete a tutoring round, refresh, and restart the service | Restore materials, conversations, attempts, and review order |
| Both model backends | Run the same minimal workflow with an API and with the ChatGPT-authenticated Codex CLI | Both return the same application schema and produce supported explanations and questions. Timeouts or invalid responses preserve submitted work |
| Matching interface and Tutor language | Select Simplified Chinese and English in turn. Use the same English course material, ask a question in Chinese, submit an answer in English, and trigger a file error | Interface copy, topics, explanations, questions, and feedback follow the selected language. Citations retain the source wording. The file error uses the interface language |
| Language switch during review | Enter part of a check answer. Switch languages during a Tutor job or with a previous conversation open, then restart | Only Tutor content in the selected language appears. Keep the check ID, entered answers, results, and progress. Restore the selected language after restart |
| Recovery and retries | Resend an identical request and simulate a parsing or model failure | Preserve existing files and answers. Produce one valid result per operation and offer a retry for the affected step |

#### 8.2 Pilot metrics

| Metric | Measurement |
| --- | --- |
| Time to find what to review | Measure from opening a course to identifying a topic that a question or reviewer confirms needs review |
| Gap diagnosis accuracy | Have a teaching assistant independently read the same answer, explanation, and short check. Measure agreement on confirmed gaps and record missed and pending gaps |
| Citation correctness | Check that a citation opens and its source location supports the explanation |
| Independent practice | Record whether the student solves a new question on the same topic without hints and gives correct key reasoning |
| Processing stability | Record parsing and generation success rates, failure stages, retries, and waiting times |

Gemini study notebooks or StudyFetch can serve as a pilot baseline. Compare time to find a review topic and gap accuracy using the same materials, tasks, and time budget. Establish a small pilot baseline before setting numerical thresholds for later versions. [Gemini study notebooks](https://blog.google/innovation-and-ai/products/gemini-app/gemini-study-notebooks/) · [StudyFetch](https://www.studyfetch.com/support)

#### 8.3 Initial acceptance fixtures

The initial acceptance input is the student-provided local file `7. Hypothesis Testing.pdf` (UFUG2104 Applied Statistics, 125 pages). Count physical pages in each uploaded file starting at 1. The answers below are test cases. Collect real student answers and metrics during the pilot.

| Expected outline | Course references to verify |
| --- | --- |
| Hypothesis testing concepts | Page 16 for what failure to reject means, page 32 for the two error types, pages 38–39 for p-values, pages 40–42 for one- and two-tailed rejection regions, and page 49 for power |
| Hypothesis testing in the normal case | Pages 58–81 for tests about a population mean (page 81 compares z-tests and t-tests), and pages 98–102 for tests about a population variance |
| Two-population hypothesis testing and A/B testing | Page 115 for two population means and page 118 for two population proportions |

The repeated agendas on pages 2, 3, 55, and 112 produce one topic tree. Each source link opens the corresponding page. On page 125, pypdf extracts the title and page number. The Tutor uses that extractable text when citing the page. The code visible on the page is unavailable as text evidence.

| Answer format | Repeatable acceptance case and expected result |
| --- | --- |
| Text blank and gap diagnosis | The student says, “p is greater than 0.05, so the null hypothesis is true.” The Tutor asks for their reasoning and uses pages 16 and 38–39 to frame a suspected gap. A new website conversion scenario gives p = 0.08 and α = 0.05 and asks for the decision and reasoning. “This proves the null hypothesis is true” marks the gap “Needs review.” “Not significant” alone leaves it “Awaiting confirmation.” “There is insufficient evidence to reject, and the null could still be false” marks it “Not confirmed.” For a confirmed gap, use another new check on the same concept, for example with p = 0.03 and α = 0.01. A correct decision with the same key reasoning removes the gap from the review list. |
| Single choice | Use a new scenario where the null hypothesis is true and the test rejects it. “Type I error” is correct, supported by page 32. |
| TeX blank | Give a Type II error probability of 0.2 under a specified alternative and ask for the power. Based on page 49, accept `0.8`, `\frac{4}{5}`, and `1-0.2`. Mark `0.2` incorrect. |

To test scanned pages, create a two-page PDF from the original. Retain the text layer on original page 124 and render original page 125 as an image-only page. Page 1 of the copy remains usable, and page 2 reports that text is unavailable. To test missing material, first upload original pages 1–111, including the agenda. Then add pages 112–125 as a second PDF. A/B testing shows “Missing material” before the second upload and can cite pages 4 and 7 of the added file afterward.

Use fixed model outputs to verify the interface, state rules, language switching, and restoration after restart. Then run the same workflow with both real model backends.

### 9. Proposed development order

1. **Local foundation and test fixtures.** Build the course view, bilingual copy and language setting, SQLite storage, and local data directory. Use the PDF and expected results in section 8.3.
2. **Import and topic outline.** Implement PDF parsing, source locations, unreadable page messages, missing topics, and additional uploads. Verify course states with fixed model responses.
3. **Tutor and review list.** Implement student questions, reasoning prompts, the three answer formats, independent checks, and evidence-based statuses. Verify that study can resume after restart.
4. **Model integration.** Connect the API and Codex CLI. Verify that both use the same output schema, language setting, citation validation, and recovery rules.
5. **Acceptance with real materials.** Run the workflow using the hypothesis testing material. During the pilot, record time to find review material, agreement on gaps, citation accuracy, and generation time. Use the results to set numerical targets.

### 10. Requirements evidence

- The project survey and four walkthrough interviews support the need to find review topics, receive feedback on specific gaps, and keep explanations consistent with course materials. [Survey summary](C:/Users/Asbab/Downloads/surveyfull.docx) · [Interview transcript](<C:/Users/Asbab/Downloads/interview transcript.docx>)
- Market research records the campus system for predefined physics questions and its formula input. The MVP generates a Tutor from the student's own materials across subjects and accepts questions they ask themselves. [Market research report](<C:/Users/Asbab/Downloads/AI Tutor Market Research Report.pptx>)

<a name="ui-copy"></a>

## 界面文案 / UI copy

文案资源按键管理。界面显示当前 `locale` 的文案，运行时填入文件名、页码和其他变量。Tutor 生成的标题、讲解、题目和反馈使用同一个语言设置。

Use the same keys in both locale files. Render copy for the active `locale` and fill in filenames, page numbers, and other variables at runtime. Tutor-generated titles, explanations, questions, and feedback follow the same language setting.

| Key | 简体中文 `zh-Hans` | English `en` |
| --- | --- | --- |
| `settings.language` | 界面和 Tutor 语言 | Interface and Tutor language |
| `settings.language.zhHans` | 简体中文 | 简体中文 |
| `settings.language.en` | English | English |
| `course.title` | 我的课程 | My courses |
| `course.create` | 新建课程 | Create course |
| `materials.title` | 课程课件 | Course materials |
| `materials.upload` | 上传课件 | Upload materials |
| `materials.add` | 补传材料 | Add missing materials |
| `materials.queued` | 等待处理 | Queued |
| `materials.parsing` | 正在读取课件… | Reading materials… |
| `materials.generating` | 正在生成辅导内容… | Generating Tutor content… |
| `materials.ready` | 可以开始复习 | Ready to review |
| `materials.failed` | 课件处理失败 | Could not process materials |
| `materials.missing` | 材料缺失 | Missing material |
| `sourceNoPreview` | 打开原件查看这处课件。 | Open the original to view this source. |
| `materials.unsupportedFormat` | 请选择 PDF 文件。 | Choose a PDF file. |
| `topics.title` | 知识点目录 | Topic outline |
| `tutor.newQuestion` | 提一个新问题 | Ask a new question |
| `tutor.reasoningPrompt` | 写下你下一步会怎么做。 | Describe what you would do next. |
| `tutor.send` | 发送 | Send |
| `tutor.loadingLanguage` | 正在加载所选语言的辅导内容… | Loading Tutor content in the selected language… |
| `tutor.retryLanguage` | 辅导内容暂未加载。请重试。 | Tutor content could not load. Try again. |
| `tutor.afterSaveError` | 辅导暂时不可用。已保存你的作答。 | Tutoring is temporarily unavailable. Your answer was saved. |
| `sources.title` | 课件依据 | Source material |
| `sources.open` | 查看原文 | View source |
| `sources.page` | 第 {number} 页 | Page {number} |
| `sources.slide` | 第 {number} 张幻灯片 | Slide {number} |
| `sources.paragraph` | 第 {number} 段 | Paragraph {number} |
| `sources.prerequisite` | 前置知识补充 | Prerequisite explanation |
| `check.title` | 无提示短题 | Independent check |
| `check.textPlaceholder` | 输入答案 | Enter your answer |
| `check.texPlaceholder` | 输入 TeX | Enter TeX |
| `check.texPreview` | 公式预览 | Formula preview |
| `check.submit` | 提交作答 | Submit answer |
| `review.title` | 复习清单 | Review list |
| `review.notAssessed` | 未诊断 | Not assessed |
| `review.pending` | 待确认 | Awaiting confirmation |
| `review.needsReview` | 待复习 | Needs review |
| `review.notConfirmed` | 本次未确认 | Not confirmed |
| `review.insufficientEvidence` | 证据不足，请补充关键步骤。 | Add a key step so the Tutor can check your reasoning. |
| `review.resolved` | 本轮复习完成 | Review complete |
| `common.retry` | 重试 | Retry |
