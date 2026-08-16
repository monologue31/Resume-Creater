#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
面接台本から「短時間版ブリーフ」を機械生成する（interview/ 専用）

なぜ手で作らないのか（教訓2）:
  同じ内容を複数ファイルで手動同期すると必ずズレる。台本を1文字直すたびに
  ブリーフ側も直す運用は、必ずどこかで抜ける——しかも本番当日に手元に置くのは
  ブリーフの方なので、ズレたときの実害が最も大きい。
  したがって **台本を単一の情報源とし、ブリーフはそこから機械生成する**。

編集判断（どのセクションを載せるか／完全版と短縮版のどちらを載せるか）は
**台本側の HTML コメントに書く**。本スクリプトは中身を一切知らない汎用の抽出器。

  <!--BRIEF:full-->    直後のセクションを丸ごと載せる
  <!--BRIEF:short-->   直後のセクションから「短縮版」だけを載せる
                       （Q・見出し・注意書きは残し、完全版の回答ブロックを落とす。
                         そのセクションに短縮版が無ければ、あるものをそのまま載せる）
  マークの無いセクションは載せない。

⚠️ 応募先・ラウンドに依存しない（ARCHITECTURE.md 2-9 d と同じ轍を踏まない）。
   `interview/companies/*/rounds/*_台本.md` を走査し、BRIEFマークを含むものだけを対象にする。

出力: 入力と同じ場所に `<元の名前>_短時間版.md`
      ⚠️ ファイル名が `_台本.md` で終わらないため、build_interview_script_pdf.py の
      自動検出（`*_台本.md`）には拾われない。ブリーフのPDFが要る場合は
      そのスクリプトに**パスを直接渡す**こと（そのための引数は実装済み）。

実行:
    python3 scripts/build_30min_brief.py                  # 対象を自動検出して全件生成
    python3 scripts/build_30min_brief.py path/to/xxx_台本.md
"""
import glob
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_GLOB = os.path.join(BASE, "interview", "companies", "*", "rounds", "*_台本.md")
MARK_RE = re.compile(r"^<!--\s*BRIEF:(full|short)\s*-->\s*$")
HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)$")
SHORT_MARK_RE = re.compile(r"^\*\*(?:⏱️\s*)?短縮版")
QUOTE_RE = re.compile(r"^>")


def split_sections(lines):
    """(見出し行, マーク or None, 本文行リスト) のリストに分解する。
    見出しの直後の行が BRIEF マークならそれを採用する。"""
    sections = []
    cur = None
    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln)
        if m:
            cur = {"heading": ln, "mark": None, "body": []}
            sections.append(cur)
            continue
        if cur is None:
            continue
        mm = MARK_RE.match(ln)
        if mm and cur["mark"] is None and not cur["body"]:
            cur["mark"] = mm.group(1)
            continue
        cur["body"].append(ln)
    return sections


def shorten(body):
    """完全版の回答ブロックを落とし、短縮版だけを残す。

    走査ルール: 引用ブロック(`>` 連続行)は、**直前に短縮版マークがあれば残し、
    無ければ落とす**。ただしセクション内に短縮版が1つも無い場合は、
    落とすと情報がゼロになるため、そのセクションはそのまま返す。
    引用以外の行（Q・小見出し・注意書き）は常に残す。
    """
    if not any(SHORT_MARK_RE.match(l) for l in body):
        return body

    out = []
    prev_was_short_mark = False
    i = 0
    n = len(body)
    while i < n:
        ln = body[i]
        if QUOTE_RE.match(ln):
            block = []
            while i < n and (QUOTE_RE.match(body[i]) or (body[i].strip() == "" and
                             i + 1 < n and QUOTE_RE.match(body[i + 1]))):
                block.append(body[i])
                i += 1
            if prev_was_short_mark:
                out.extend(block)
            prev_was_short_mark = False
            continue
        if SHORT_MARK_RE.match(ln):
            prev_was_short_mark = True
        elif ln.strip():
            prev_was_short_mark = False
        out.append(ln)
        i += 1
    return out


def build(src):
    raw = open(src, encoding="utf-8").read()
    lines = raw.split("\n")
    sections = split_sections(lines)
    picked = [s for s in sections if s["mark"]]
    if not picked:
        return None, 0

    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("# ") else os.path.basename(src)
    out = [
        f"# {title} — 短時間版ブリーフ",
        "",
        # 組版指示: セクションごとの改ページを止める（短時間版はページ数を抑えることが目的のため）。
        # build_interview_script_pdf.py がこのマークを見て詰めて組む。
        "<!--COMPACT-->",
        "",
        "【注意】**このファイルは自動生成物。直接編集しないこと。**",
        f"元ファイル `{os.path.basename(src)}` を単一の情報源として、"
        "`scripts/build_30min_brief.py` が抽出している（教訓2: 手動同期は必ずズレる）。"
        "内容を直すときは元ファイルを直し、本スクリプトを再実行する。",
        "",
        "【注意】**回答は短縮版のみを載せている。** "
        "掘り下げられた時に使う完全版・詳細な判断理由は元の台本と元のラウンド記録にある。",
        "",
        "---",
        "",
    ]
    for s in picked:
        body = s["body"] if s["mark"] == "full" else shorten(s["body"])
        out.append(s["heading"])
        # 先頭・末尾の空行を詰める
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        out.extend([""] + body + ["", "---", ""])

    dst = re.sub(r"\.md$", "_短時間版.md", src)
    text = "\n".join(out).rstrip() + "\n"
    open(dst, "w", encoding="utf-8").write(text)
    return dst, len(picked)


if __name__ == "__main__":
    targets = [os.path.abspath(a) for a in sys.argv[1:]] or sorted(glob.glob(SRC_GLOB))
    made = 0
    for src in targets:
        if src.endswith("_短時間版.md"):
            continue
        dst, n = build(src)
        if dst:
            made += 1
            print("OK", os.path.relpath(dst, BASE), f"{n}セクション", os.path.getsize(dst), "bytes")
    if not made:
        raise SystemExit(
            "BRIEFマーク（<!--BRIEF:full--> / <!--BRIEF:short-->）を含む台本が見つかりません。\n"
            "  → 載せたいセクションの見出しの直後にマークを1行入れてください。")
