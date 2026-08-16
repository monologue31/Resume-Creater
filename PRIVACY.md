# Privacy and Sharing

## 分享前检查

1. 从空目录按白名单复制，不要直接压缩日常工作目录。
2. 不复制真实 `input/`、`documents/output/`、`interview/companies/`、`archive/`、照片、证书、录音、转录或本地设置。
3. 创建本地 `privacy_terms.local.txt`，每行写一个不应出现的姓名、公司、电话片段、邮件、地址或其他标识符。
4. 运行 `python3 scripts/audit_privacy.py`。
5. 检查 PDF 的文本层、元数据、文件名和压缩包清单。

`privacy_terms.local.txt` 会被 `.gitignore` 排除。它是扫描输入，本身也是敏感文件，不应进入分享包。

## 扫描局限

自动扫描只能发现常见模式和已知词。它不能证明“一定没有”隐私泄露，因此最后仍需要人工审查。
