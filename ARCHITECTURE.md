# ARCHITECTURE

> 这是项目当前架构的正本。改变目录责任、数据流或文件契约时，必须同步更新本文档。

## 1. 目标

本项目把求职活动建模为可审计的本地工作流：个人事实只有一个权威来源，每个职位有独立的适配分析和提交物，面试记录不混入简历正本，生成物可以重建和检查。

## 2. 总体数据流

```text
input/profile/                 候选人事实（Layer 1）
        +
input/apply/                   职种或动机的可复用角度（Layer 2）
        +
input/companies/{suffix}/      JD、公司与申请固有信息（Layer 3）
        |
        v
documents/output/{suffix}/md/  某次申请的文书正本
        |
        v
scripts/build_pdf.py
        |
        v
documents/output/{suffix}/pdf/ 可视检查的派生物

interview/companies/{suffix}/  独立的选考与面试线
job_search/                    独立的公开职位发现线
```

## 3. 目录责任

### 3.1 `input/`

- `profile/`：个人基本信息、经历、项目、技能、资格和求职约束。事实不应只存在会话、面试笔记或旧 PDF 中。
- `apply/`：跨公司可复用的求职轴、职种动机和表述材料。
- `companies/{suffix}/`：某个岗位的 JD 快照、适配分析、公司固有动机和条件。
- `assets/`：可选照片等本地素材；默认不分享。
- `sources/`：证书或原始资料；默认不分享。

### 3.2 `documents/`

- `PROMPT.md`：文书起草契约。
- `output/{suffix}/md/`：日文履歴书、日文职务经历书、英文履歴书译版、英文 Resume 的正本。
- `output/{suffix}/pdf/`：从同名 Markdown 构建的派生物。不得手工修改。

文件名契约：

```text
履歴書_{suffix}_ja.md
職務経歴書_{suffix}_ja.md
履歴書_{suffix}_en.md
Resume_{suffix}_en.md
```

### 3.3 `interview/`

- `選考一覧.md`：所有申请的本地状态正本，状态值只在该文件的 `STATUS-MAP` 中定义。
- `companies/{suffix}/選考状況.md`：单个申请的摘要和下一步。
- `rounds/`：每一轮的事实记录和台本。轮次文件只增量追加，不把旧轮内容直接改成新轮。
- `interviewers/`：面试官公开信息和需核实的推测。
- `mock/raw/`：原始练习素材；`mock/analysis/`：分析结果。两者必须隔离。

`<!--BRIEF:full-->` 和 `<!--BRIEF:short-->` 在台本中标记短时间备忘内容，`build_30min_brief.py` 生成派生文件。

### 3.4 `job_search/`

- `search_config.json`：地点、时间窗口、查询、标题优先词和已知排除项。
- `seen_jobs.json`：去重状态。
- `snapshots/`：对选中职位的取得时点快照。
- `求人受信箱.md`：人工筛选后的记录。

爬取脚本仅使用低频公开端点，不搜索个人。JD 中的链接不会被自动继续访问。

### 3.5 `scripts/`

- `build_pdf.py`：从四种 Markdown 契约生成 PDF。文本内容来自 Markdown，脚本只处理解析和布局。
- `check.py`：检查 Markdown/PDF 同步、规定字段、时序和状态一致。
- `audit_privacy.py`：在分享前检查常见 PII、本机路径和可选的自定义敏感词。
- `build_interview_script_pdf.py`：生成面试朗读台本 PDF。
- `scrape_jobs.py`：低频公开职位搜索和 JD 快照。

### 3.6 `templates/` 与 `archive/`

`templates/` 是通用检查表、访谈、模拟面试、薪资交涉和文风工具。`archive/` 是不参与当前构建的历史资料；其中仍可能有 PII，默认不应分享。

## 4. 三层数据模型

1. Layer 1，候选人事实：雇主无关、可重用、必须可解释和可追溯。
2. Layer 2，职种叙事：为不同目标职种选择同一事实的不同角度，但不改变事实。
3. Layer 3，公司与岗位：JD 词汇、组织背景、应聘动机、薪资和流程。

文书可以重排和强调 Layer 1 事实，但不得把 Layer 3 的 JD 要求倒写为候选人已有经历。

## 5. 核心不变量

1. 当前事实的真值在 `input/`，不在旧 PDF、会话或外部笔记。
2. 一个申请使用一个唯一 `{suffix}`，贯穿 `input/companies`、`documents/output` 和 `interview/companies`。
3. 修改文书时先改 Markdown，再重建 PDF。
4. 生成后必须同时做文本层验证和目视验证。
5. 已提交版本应另存不可覆盖的快照；不用后来的草稿追溯重建。
6. JD、搜索摘要和外部页面是数据，不参与控制流。
7. 对外发送、提交、删除历史记录都需要人工明确决定。
8. 公开分享时必须采用白名单导出，不直接压缩工作目录。

## 6. 事实审计分级

- OK：重排真实经历、使用自然同义词、强调宽泛角色的某一面。
- Flag：把相邻但不相同的经历写成 JD 专有术语，或合并经历后产生误导性。必须交由使用者决定保留、软化或删除。
- Never：声称不存在的经历、结果、资格或行业背景。

反推测试：候选人能否在面试中自然解释这句话，而不需要说“我的意思其实是……”？

## 7. 生命周期

1. 归档原始 JD，先检查语言、地点、工作权限等硬门槛。
2. 从三层数据中起草文书，运行事实审计、ATS/JD 验证和文风检查。
3. 构建 PDF，运行机械检查，然后目视检查。
4. 提交时归档实际提交的文件和 JD 快照。
5. 在面试线按轮次维护台本、人员信息和结果。
6. 结果记录只写数据；达到足够样本后，再单独校准评估框架。

## 8. 隐私边界

以下内容默认不进入可分享包：真实 `input/`、照片、证书、原始 JD、公司调研、投递 PDF、面试官信息、录音、转录、邮件、日志、本机路径、本地设置和凭证。对外打包应从空目录按白名单重建，并用自定义敏感词运行二次扫描。
