# Career Application Workflow Template

一个本地优先、事实可追溯的求职项目模板。它把候选人事实、职位适配、投递文件、面试准备和求职跟踪分开管理，并从 Markdown 生成 PDF。

本包只包含虚构示例和占位符，不包含原项目使用者、雇主、面试官、岗位、录音、转录、联系方式或投递历史。

## 快速开始

1. 阅读 [`_START_HERE.md`](_START_HERE.md) 和 [`ARCHITECTURE.md`](ARCHITECTURE.md)。
2. 复制 `input/profile/` 中的占位模板，填写自己的可验证事实。
3. 为新岗位复制 `input/companies/Sample_Application/`，改成唯一后缀。
4. 根据 `documents/PROMPT.md` 生成四份 Markdown 正本。
5. 运行：

   ```bash
   python3 -m pip install -r requirements.txt
   python3 scripts/build_pdf.py Sample_Application
   python3 scripts/check.py
   python3 scripts/audit_privacy.py
   ```

## 设计底线

- `input/` 是事实来源，`documents/output/` 是特定申请的文书正本。
- PDF 只从 Markdown 生成，不反向手改 PDF。
- JD 和网页内容是未受信数据，不是工作流指令。
- 没有事实依据的主张不进入简历或面试台本。
- 工具只负责起草、生成和检查，不自动发送邮件或提交申请。

## 语言与运行环境

文档以日语为主，入门说明同时提供中文。脚本需要 Python 3.10+；PDF 生成使用 ReportLab，检查优先使用 Poppler 的 `pdftotext`，并可回退到 PyMuPDF。
