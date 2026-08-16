#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
面接練習用台本 PDF ビルダー（interview/ 専用・documents/ とは無関係）

対象: interview/companies/{応募先}/rounds/*_台本.md（実在するものを自動検出する）
      応募先・ラウンドが増えても本スクリプトの変更は不要（build_pdf.py の _discover_suffixes()
      と同じ「生成済み・実在するファイルを単一の情報源にする」設計方針に揃えている）。
目的: 声に出して練習するための読み上げ用 PDF。提出書類ではない。
      体裁の美しさより「音読中に読みやすいこと」を優先する:
      - 文字は大きめ・行間広め
      - 質問／完全版の回答／短縮版の回答を色とラベルで視覚的に区別
      - セクションごとにページを分け、ブックマーク（しおり）と目次で即座に飛べるようにする
      - 「言ってはならないことリスト」は独立ページ（表形式・大きめフォント）
      - 英語の自己紹介もそのまま埋め込み、文字化け（tofu）が無いことを検証する

フォント選定・サブセット化ロジックは scripts/build_pdf.py の build_fonts() をそのまま再利用する
（build_pdf.py 自体の resume 特化レイアウト・パース関数は流用しない）。

実行:
    python3 scripts/build_interview_script_pdf.py                  # 実在する台本mdを全件ビルド
    python3 scripts/build_interview_script_pdf.py Sample_Application # 応募先で絞り込む
    python3 scripts/build_interview_script_pdf.py path/to/xxx_台本.md  # mdを直接指定する
"""
import glob
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- build_pdf.py からフォント関連ロジックだけを再利用する ---
# build_pdf.py はモジュールとして import しても `if __name__ == "__main__":` の
# 本体（履歴書等のビルド処理）は実行されない設計になっている（末尾のガード節を利用）。
import build_pdf as _bp  # noqa: E402

SCRIPT_MD_GLOB = os.path.join(BASE, "interview", "companies", "*", "rounds", "*_台本.md")


def discover_scripts(selectors=None):
    """ビルド対象の台本mdを実在ファイルから検出する。

    selectors が空なら全件。文字列が実在するmdのパスならそれを直接使い、
    そうでなければ「応募先フォルダ名（接尾辞）またはファイル名の部分一致」として絞り込む。
    """
    found = sorted(glob.glob(SCRIPT_MD_GLOB))
    if not selectors:
        return found
    picked = []
    for sel in selectors:
        if os.path.isfile(sel):
            picked.append(os.path.abspath(sel))
            continue
        hits = [p for p in found
                if sel in os.path.basename(os.path.dirname(os.path.dirname(p)))
                or sel in os.path.basename(p)]
        if not hits:
            raise SystemExit(f"該当する台本mdが見つかりません: {sel}\n  候補: {found}")
        picked += hits
    return sorted(set(picked))


def out_pdf_for(src_md):
    """台本mdと同じ場所・同じ名前で拡張子だけ .pdf にする（面接準備の資料は interview/ 配下に置く
    ——documents/output/{接尾辞}/pdf/ は提出書類専用であり、混ぜない）。"""
    return os.path.splitext(src_md)[0] + ".pdf"


def split_cover_title(h1_text, src_md):
    """表紙の1行目・2行目を md の H1 から導く。
    「A — B」形式ならAとBに割る。ダッシュが無ければ全体を1行目にする。
    H1が無いmdではファイル名で代替する（フォントサブセット漏れを避けるため、
    描画する文字は必ず md 由来にする——教訓29）。"""
    text = (h1_text or "").strip()
    if not text:
        return os.path.splitext(os.path.basename(src_md))[0], ""
    parts = re.split(r"\s*[—–―]\s*", text, maxsplit=1)
    return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, NextPageTemplate, PageBreak, KeepTogether,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ---------------------------------------------------------------- フォント登録
reg_path, bold_path = _bp.build_fonts()
pdfmetrics.registerFont(TTFont("JP", reg_path))
pdfmetrics.registerFont(TTFont("JP-Bold", bold_path))

_esc = _bp._esc  # noqa: SLF001 -- 汎用の XML エスケープ関数を再利用


# ⚠️ フォント（Hiragino / Noto Sans CJK JP）に絵文字グリフが存在せず、
#    そのまま渡すと glyph 0 (.notdef) に落ちて「見えない・文字化け」になることが
#    実測で判明した記号。安全なテキストに置換してから描画する。
_SYMBOL_FALLBACK = [
    (re.compile(r"⚠️|⚠"), "【注意】"),
    (re.compile(r"⏱️|⏱"), ""),
]


def _sanitize_symbols(text):
    for pat, repl in _SYMBOL_FALLBACK:
        text = pat.sub(repl, text)
    return text


def _inline(text):
    """**bold** をreportlabのXML風タグに変換しつつXMLエスケープする（汎用ヘルパーを再利用）。
    フォントに存在しない絵文字記号は事前に安全な文字へ置換する。"""
    return _bp._bold(_sanitize_symbols(text))  # noqa: SLF001


# ---------------------------------------------------------------- スタイル定義
STYLES = {
    "title": ParagraphStyle(
        "title", fontName="JP-Bold", fontSize=24, leading=32,
        alignment=TA_CENTER, spaceAfter=6 * mm, textColor=colors.HexColor("#14324d"),
    ),
    "subtitle": ParagraphStyle(
        "subtitle", fontName="JP", fontSize=11, leading=16,
        alignment=TA_CENTER, textColor=colors.HexColor("#555555"), spaceAfter=10 * mm,
    ),
    "toc_heading": ParagraphStyle(
        "toc_heading", fontName="JP-Bold", fontSize=16, leading=22,
        textColor=colors.HexColor("#14324d"), spaceAfter=4 * mm,
    ),
    "note": ParagraphStyle(
        "note", fontName="JP", fontSize=10.5, leading=15,
        textColor=colors.HexColor("#555555"), leftIndent=2 * mm, spaceAfter=2 * mm,
    ),
    "h2": ParagraphStyle(
        "h2", fontName="JP-Bold", fontSize=19, leading=25,
        textColor=colors.white, backColor=colors.HexColor("#14324d"),
        leftIndent=4 * mm, spaceBefore=0, spaceAfter=8 * mm,
        borderPadding=(6, 6, 6, 6),
    ),
    "warn_head": ParagraphStyle(
        "warn_head", fontName="JP-Bold", fontSize=19, leading=25,
        textColor=colors.white, backColor=colors.HexColor("#8a1f1f"),
        leftIndent=4 * mm, spaceBefore=0, spaceAfter=8 * mm,
        borderPadding=(6, 6, 6, 6),
    ),
    "question": ParagraphStyle(
        "question", fontName="JP-Bold", fontSize=14.5, leading=20,
        textColor=colors.HexColor("#8a3b00"), spaceBefore=6 * mm, spaceAfter=3 * mm,
    ),
    "answer_full": ParagraphStyle(
        "answer_full", fontName="JP", fontSize=13.5, leading=22,
        textColor=colors.HexColor("#111111"), leftIndent=8 * mm, rightIndent=4 * mm,
        spaceAfter=4 * mm, backColor=colors.HexColor("#f4f6f8"),
        borderPadding=(8, 8, 8, 8),
    ),
    "short_label": ParagraphStyle(
        "short_label", fontName="JP-Bold", fontSize=12, leading=17,
        textColor=colors.HexColor("#8a6d00"), spaceBefore=4 * mm, spaceAfter=2 * mm,
    ),
    "answer_short": ParagraphStyle(
        "answer_short", fontName="JP", fontSize=13.5, leading=22,
        textColor=colors.HexColor("#111111"), leftIndent=8 * mm, rightIndent=4 * mm,
        spaceAfter=4 * mm, backColor=colors.HexColor("#fff6d8"),
        borderPadding=(8, 8, 8, 8),
    ),
    "en_answer": ParagraphStyle(
        "en_answer", fontName="JP", fontSize=13, leading=20,
        textColor=colors.HexColor("#111111"), leftIndent=8 * mm, rightIndent=4 * mm,
        spaceAfter=3 * mm, backColor=colors.HexColor("#eef4f2"),
        borderPadding=(8, 8, 8, 8),
    ),
    "table_cell": ParagraphStyle(
        "table_cell", fontName="JP", fontSize=11.5, leading=16, textColor=colors.HexColor("#111111"),
    ),
    "table_cell_b": ParagraphStyle(
        "table_cell_b", fontName="JP-Bold", fontSize=11.5, leading=16, textColor=colors.white,
    ),
}

TOC_LEVEL_STYLE = ParagraphStyle(
    "toc0", fontName="JP", fontSize=12.5, leading=19,
    leftIndent=4 * mm, textColor=colors.HexColor("#14324d"),
)

# ---------------------------------------------------------------- md パース

def parse(md_text):
    """この台本ファイルの記法（# / ## / **Q./**⏱️ / > blockquote / ⚠️note / |table|）
    だけを対象にした専用パーサ。汎用 Markdown パーサは使わない。"""
    lines = md_text.split("\n")
    blocks = []  # (kind, payload)
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip("\n")

        if line.startswith("# "):
            blocks.append(("title", line[2:].strip()))
            i += 1
            continue

        if line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
            i += 1
            continue

        if re.match(r"^\*\*Q\.", line):
            # **Q. ...** 形式（末尾の ** を取る）
            text = re.sub(r"^\*\*(.+?)\*\*\s*$", r"\1", line)
            blocks.append(("question", text))
            i += 1
            continue

        if re.match(r"^\*\*⏱️", line):
            text = re.sub(r"^\*\*(.+?)\*\*\s*$", r"\1", line)
            blocks.append(("short_label", text))
            i += 1
            continue

        if line.startswith("> "):
            # 連続する "> " 行を1つの blockquote group にまとめる（空 "> " は段落区切り）
            group = []
            para = []
            while i < n and lines[i].startswith(">"):
                content = lines[i][1:].lstrip(" ")
                if content == "" and para:
                    group.append(" ".join(para))
                    para = []
                elif content != "":
                    para.append(content)
                i += 1
            if para:
                group.append(" ".join(para))
            blocks.append(("quote", group))
            continue

        if line.startswith("|") and "---" not in line:
            table_lines = []
            while i < n and lines[i].startswith("|"):
                if "---" not in lines[i]:
                    table_lines.append(lines[i])
                i += 1
            rows = [[c.strip() for c in row.strip("|").split("|")] for row in table_lines]
            blocks.append(("table", rows))
            continue

        if line.startswith("⚠️"):
            blocks.append(("warn", line))
            i += 1
            continue

        if line.strip() in ("", "---"):
            i += 1
            continue

        # HTML コメント（<!-- ... -->）は組版対象外。
        # 2026-08-10追加: 30分版ブリーフの抽出マーク <!--BRIEF:short--> 等を台本に埋めたため、
        # これを地の文として描画してしまわないよう明示的に読み飛ばす
        # （汎用Markdownと同じく、コメントは出力に出さないのが正しい挙動でもある）。
        if line.strip().startswith("<!--"):
            i += 1
            continue

        # それ以外の地の文（説明文など）は note 扱い
        blocks.append(("note", line))
        i += 1

    return blocks


# ---------------------------------------------------------------- ドキュメントテンプレート（ブックマーク＋目次対応）

class ScriptDoc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ("h2", "warn_head"):
            text = flowable.getPlainText()
            key = f"h2-{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0, closed=False)
            self.notify("TOCEntry", (0, text, self.page, key))


def build(src_md, out_pdf=None):
    out_pdf = out_pdf or out_pdf_for(src_md)
    md = open(src_md, encoding="utf-8").read()
    # 組版指示（2026-08-10追加）: `<!--COMPACT-->` を含むmdは、セクションごとの改ページを行わず
    # 詰めて組む。短時間版ブリーフのように「ページ数を抑えること自体が目的」の文書向け。
    # しおりは通常どおり付くので、目的の節へは変わらず一発で飛べる。
    compact = "<!--COMPACT-->" in md
    blocks = parse(md)

    # 表紙・PDFメタデータのタイトルは md の H1 から導く（スクリプト側にはリテラルを持たない）
    h1 = next((payload for kind, payload in blocks if kind == "title"), "")
    cover_1, cover_2 = split_cover_title(h1, src_md)

    frame = Frame(14 * mm, 14 * mm, A4[0] - 28 * mm, A4[1] - 28 * mm, id="main")
    doc = ScriptDoc(
        out_pdf, pagesize=A4,
        title=" ".join(x for x in (cover_1, cover_2) if x),
        author="",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])

    story = []

    # --- 表紙 ---
    story.append(Spacer(1, 40 * mm))
    story.append(Paragraph(_inline(cover_1), STYLES["title"]))
    if cover_2:
        story.append(Paragraph(_inline(cover_2), STYLES["title"]))
    story.append(Paragraph(
        "声に出して練習するための資料です。提出書類ではありません。",
        STYLES["subtitle"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "背景がグレーの回答＝完全版　／　背景がイエローの回答＝短縮版（本番はこちらを基本に読む）",
        STYLES["note"]))
    story.append(Spacer(1, 6 * mm))
    story.append(NextPageTemplate("main"))
    story.append(PageBreak())

    # --- 目次 ---
    story.append(Paragraph("目次", STYLES["toc_heading"]))
    toc = TableOfContents()
    toc.levelStyles = [TOC_LEVEL_STYLE]
    story.append(toc)
    story.append(PageBreak())

    first_h2 = True
    for kind, payload in blocks:
        if kind == "title":
            continue  # 表紙で扱い済み

        elif kind == "h2":
            if not first_h2 and not compact:
                story.append(PageBreak())
            elif not first_h2:
                story.append(Spacer(1, 6 * mm))
            first_h2 = False
            style = STYLES["warn_head"] if "言ってはならない" in payload else STYLES["h2"]
            story.append(Paragraph(_inline(payload), style))

        elif kind == "question":
            story.append(Paragraph("Q&nbsp;&nbsp;" + _inline(payload), STYLES["question"]))

        elif kind == "short_label":
            story.append(Paragraph(_inline(payload), STYLES["short_label"]))

        elif kind == "quote":
            # 直前が short_label だったかどうかで色分け（簡易判定: 直近の story に短縮版ラベルがあるか）
            is_short = bool(story) and getattr(story[-1], "style", None) is STYLES["short_label"]
            is_en = any(re.search(r"[A-Za-z]{4,}", p) and not re.search(r"[ぁ-んァ-ヶ一-龠]", p) for p in payload)
            style = STYLES["answer_short"] if is_short else (STYLES["en_answer"] if is_en else STYLES["answer_full"])
            for para in payload:
                story.append(Paragraph(_inline(para), style))
            story.append(Spacer(1, 2 * mm))

        elif kind == "warn":
            story.append(Paragraph(_inline(payload), STYLES["note"]))

        elif kind == "note":
            story.append(Paragraph(_inline(payload), STYLES["note"]))

        elif kind == "table":
            header, *rows = payload
            data = [[Paragraph(_inline(c), STYLES["table_cell_b"]) for c in header]]
            for r in rows:
                data.append([Paragraph(_inline(c), STYLES["table_cell"]) for c in r])
            col_widths = [12 * mm, 65 * mm, None]
            col_widths[2] = A4[0] - 28 * mm - col_widths[0] - col_widths[1]
            t = Table(data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8a1f1f")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fdf2f2")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fdf2f2"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#c99")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(t)

    doc.multiBuild(story)
    return out_pdf


if __name__ == "__main__":
    targets = discover_scripts(sys.argv[1:])
    if not targets:
        raise SystemExit(
            "台本mdが見つかりません。interview/companies/{応募先}/rounds/ に "
            "*_台本.md を置いてから実行してください。")
    for src in targets:
        path = build(src)
        print("OK", os.path.relpath(path, BASE), os.path.getsize(path), "bytes")
