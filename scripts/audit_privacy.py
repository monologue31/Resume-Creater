#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共有前のプライバシー監査。

使い方:
  1. 任意でルートに privacy_terms.local.txt を作り、1行1語を記入する。
  2. python3 scripts/audit_privacy.py

終了コード 0 = 検出なし、1 = 要確認項目あり。
このスクリプトは「漏洩がない」ことを証明するものではない。最終的な人手確認は必須。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
TERMS_FILE = BASE / "privacy_terms.local.txt"
TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".csv", ".tsv", ".html", ".css", ".js", ".ts", ".xml", ".sh",
}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__"}
RAW_MEDIA_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aac", ".mov", ".mp4"}

# 意図的に広めのパターン。誤検知は人手で判定する。
PATTERNS = {
    "email": re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    "Japanese phone": re.compile(r"(?<!\d)(?:0\d{1,4}[- ]\d{1,4}[- ]\d{4}|0\d{9,10})(?!\d)"),
    "Japanese postal code": re.compile(r"(?<!\d)\d{3}-\d{4}(?!\d)"),
    "macOS home path": re.compile(r"/Users/[^/\s]+"),
    "Windows home path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.I),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def iter_files():
    for path in BASE.rglob("*"):
        if not path.is_file() or path.resolve() in {SELF, TERMS_FILE.resolve()}:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(BASE).parts):
            continue
        yield path


def load_terms() -> list[str]:
    if not TERMS_FILE.exists():
        return []
    return [line.strip() for line in TERMS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def read_searchable_text(path: Path) -> str | None:
    if path.suffix.lower() in TEXT_EXTENSIONS or not path.suffix:
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None
    if path.suffix.lower() == ".pdf":
        try:
            import fitz
            with fitz.open(path) as doc:
                metadata = "\n".join(str(value or "") for value in doc.metadata.values())
                body = "\n".join(page.get_text() for page in doc)
            return metadata + "\n" + body
        except Exception:
            return None
    return None


def main() -> int:
    terms = load_terms()
    findings: list[str] = []
    unreadable_pdfs: list[str] = []

    for path in iter_files():
        rel = path.relative_to(BASE)
        rel_text = str(rel)
        if path.suffix.lower() in RAW_MEDIA_EXTENSIONS:
            findings.append(f"raw media: {rel_text}")

        for term in terms:
            if term.casefold() in rel_text.casefold():
                findings.append(f"custom term in filename: {rel_text} / {term!r}")

        text = read_searchable_text(path)
        if text is None:
            if path.suffix.lower() == ".pdf":
                unreadable_pdfs.append(rel_text)
            continue

        for label, pattern in PATTERNS.items():
            match = pattern.search(text)
            if match:
                findings.append(f"{label}: {rel_text} / {match.group(0)!r}")
        for term in terms:
            if term.casefold() in text.casefold():
                findings.append(f"custom term: {rel_text} / {term!r}")

    if TERMS_FILE.exists():
        print(f"自定義敏感詞: {len(terms)}件を読み込み")
    else:
        print("注意: privacy_terms.local.txt は未設定（汎用パターンのみ検査）")

    if unreadable_pdfs:
        print("警告: テキスト/メタデータを読めないPDF:")
        for item in unreadable_pdfs:
            print(f"  - {item}")

    if findings:
        print(f"要確認: {len(findings)}件")
        for item in sorted(set(findings)):
            print(f"  - {item}")
        return 1

    print("検出なし: 自動パターンに該当する項目はありません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
