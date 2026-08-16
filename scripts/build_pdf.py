#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
履歴書・職務経歴書 PDF ビルダー

output/*.md の内容を、日本語フォント埋め込みの A4 PDF として出力する。
- 日本語フォント: Noto Sans CJK JP（CFF→TTF 変換のうえサブセット埋め込み）
- 実行: python3 scripts/build_pdf.py
"""
import os, sys, glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "documents", "output")   # 応募書類の出力先

# ⚠️ 2026-08-10、応募先ごとのサブフォルダ構成へ変更（本人指示）。
#   旧: documents/output/{md,pdf}/職務経歴書_{接尾辞}_ja.md
#   新: documents/output/{接尾辞}/{md,pdf}/職務経歴書_{接尾辞}_ja.md
# 応募先が増えるほど1つのmd/フォルダにファイルが混在して見分けがつかなくなるため、
# `input/companies/{接尾辞}/`・`interview/companies/{接尾辞}/` と同じ「応募先ごとに1フォルダ」
# の形に揃えた。md/pdf という形式ごとの分割は各応募先フォルダの中で維持している。
# 詳細: ARCHITECTURE.md 2-11節。


def _out_dir(suffix, kind):
    """応募先の接尾辞と種別（"md" / "pdf"）から出力ディレクトリを返す。
    パスの組み立てはここに集約する——他の場所でos.path.joinしないこと。"""
    return os.path.join(OUT, suffix, kind)
INTERVIEW_OUT = os.path.join(BASE, "interview")
FONTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
PHOTO_PATH = os.path.join(BASE, "input", "assets", "photo.jpg")  # 証明写真（2026-08-07: 実際に埋め込むよう修正）

# ---------------------------------------------------------------- フォント準備
# 日本語 CJK フォントの候補（環境ごとに存在するものが違うため、上から順に探す）。
# 各要素: (Regular の .ttc/.otf パス, Regular の fontNumber, Bold の パス, Bold の fontNumber)
FONT_CANDIDATES = [
    # Linux（Noto Sans CJK JP。Docker/CI 等で使われる想定）
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0,
     "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    # macOS 標準搭載（ヒラギノ角ゴシック。fontNumber=2 が "Hiragino Kaku Gothic ProN"）
    ("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", 2,
     "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", 2),
]


def _font_not_found_error():
    return RuntimeError(
        "日本語フォントが見つかりませんでした。以下のいずれかを行ってください:\n"
        "  1) Linux 環境: Noto Sans CJK JP をインストール\n"
        "     例: apt-get install fonts-noto-cjk\n"
        "  2) macOS: 標準でヒラギノが入っているはずですが、見つからない場合は\n"
        "     brew install --cask font-noto-sans-cjk-jp でも代替可能\n"
        "  3) あるいは任意の日本語 TTC/OTF を用意し、\n"
        "     scripts/build_pdf.py の FONT_CANDIDATES にパスを追加してください"
    )


def build_fonts():
    """日本語フォント（CFF ベース）を reportlab が読める TTF に変換して用意する。

    変換結果は scripts/fonts/ にキャッシュする。**キャッシュは「使用文字集合のハッシュ」で
    無効化判定する**ため、input/documents/interview の内容が変わって新しい文字が増えても、
    古いキャッシュのまま無視されることはない（フォントパスが存在しないマシンでキャッシュだけ
    残っている状態で古いまま固定されてしまう事故を防ぐため）。
    """
    os.makedirs(FONTDIR, exist_ok=True)
    reg = os.path.join(FONTDIR, "NotoJP-Regular.ttf")
    bld = os.path.join(FONTDIR, "NotoJP-Bold.ttf")
    hash_path = os.path.join(FONTDIR, "charset.sha256")

    chars = set()
    for root in (OUT, INTERVIEW_OUT, os.path.join(BASE, "input")):
        for p in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
            chars |= set(open(p, encoding="utf-8").read())
    chars |= set("0 1 2 3 4 5 6 7 8 9 ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz "
                 ".,/-–—()（）「」『』・：、。％%&+*#@!?〜~＆★®")
    chars = {c for c in chars if c.isprintable()}

    import hashlib
    charset_hash = hashlib.sha256("".join(sorted(chars)).encode("utf-8")).hexdigest()

    if os.path.exists(reg) and os.path.exists(bld) and os.path.exists(hash_path):
        if open(hash_path, encoding="utf-8").read().strip() == charset_hash:
            return reg, bld  # 文字集合が前回と同じなのでキャッシュを再利用

    from fontTools.ttLib import TTFont as FTFont
    from fontTools.subset import Subsetter, Options
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.ttLib.tables._g_l_y_f import table__g_l_y_f
    from fontTools.ttLib.tables._l_o_c_a import table__l_o_c_a

    def otf2ttf(font, max_err=1.0):
        order = font.getGlyphOrder(); gs = font.getGlyphSet(); glyf = {}
        for name in order:
            pen = TTGlyphPen(gs)
            try:
                gs[name].draw(Cu2QuPen(pen, max_err, reverse_direction=True))
            except Exception:
                pass
            glyf[name] = pen.glyph()
        t = table__g_l_y_f(); t.glyphs = glyf; t.glyphOrder = order
        font["glyf"] = t; font["loca"] = table__l_o_c_a()
        for name in order:
            glyf[name].recalcBounds(t)
        m = font["maxp"]; m.tableVersion = 0x00010000
        for k, v in dict(maxZones=1, maxTwilightPoints=0, maxStorage=0, maxFunctionDefs=0,
                         maxInstructionDefs=0, maxStackElements=0, maxSizeOfInstructions=0,
                         maxComponentElements=0, maxComponentDepth=0, maxPoints=0,
                         maxContours=0, maxCompositePoints=0, maxCompositeContours=0).items():
            setattr(m, k, v)
        m.numGlyphs = len(order); m.recalc(font)
        font["head"].indexToLocFormat = 0
        for tag in ("CFF ", "VORG"):
            if tag in font:
                del font[tag]
        font.sfntVersion = "\x00\x01\x00\x00"
        return font

    chosen = None
    for reg_src, reg_num, bld_src, bld_num in FONT_CANDIDATES:
        if os.path.exists(reg_src) and os.path.exists(bld_src):
            chosen = (reg_src, reg_num, bld_src, bld_num)
            break
    if chosen is None:
        raise _font_not_found_error()

    reg_src, reg_num, bld_src, bld_num = chosen
    srcs = [(reg_src, reg_num, reg), (bld_src, bld_num, bld)]
    for src, num, dst in srcs:
        f = FTFont(src, fontNumber=num)
        o = Options(); o.layout_features = []; o.name_IDs = ["*"]; o.notdef_outline = True
        o.drop_tables += ["BASE", "JSTF", "DSIG", "vhea", "vmtx", "VORG"]
        s = Subsetter(options=o); s.populate(text="".join(sorted(chars))); s.subset(f)
        otf2ttf(f).save(dst)
    with open(hash_path, "w", encoding="utf-8") as f:
        f.write(charset_hash)
    return reg, bld


REG, BLD = build_fonts()

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT, TA_CENTER
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Table, TableStyle, Spacer, KeepTogether, Image)

pdfmetrics.registerFont(TTFont("JP", REG))
pdfmetrics.registerFont(TTFont("JPB", BLD))
pdfmetrics.registerFontFamily("JP", normal="JP", bold="JPB", italic="JP", boldItalic="JPB")

INK = colors.HexColor("#111111")
LINE = colors.HexColor("#333333")
SOFT = colors.HexColor("#b9c4cf")
HEAD = colors.HexColor("#f0f0f0")
HEAD2 = colors.HexColor("#f2f5f8")
ACC = colors.HexColor("#1b3a5c")
BANNER = colors.HexColor("#eef2f6")
TODO = colors.HexColor("#cc0000")

def S(name, size=9.5, leading=None, font="JP", **kw):
    kw.setdefault("textColor", INK)
    kw.setdefault("wordWrap", "CJK")   # 日本語の折り返しを文字単位に
    kw.setdefault("splitLongWords", 0)  # 英単語を途中で割らない
    return ParagraphStyle(name, fontName=font, fontSize=size,
                          leading=leading or size * 1.56, **kw)

# 和欧混在で両端揃えにすると欧文語間が伸びて汚くなるため、左揃えを既定とする
BODY = S("body", 9.5)
CELL = S("cell", 9)
CELLB = S("cellb", 9, font="JPB")
CELLC = S("cellc", 9, alignment=TA_CENTER)
CELLR = S("cellr", 9, alignment=TA_RIGHT)
SMALL = S("small", 8.3, leading=12)
TITLE = S("title", 17, font="JPB", alignment=TA_CENTER)
META = S("meta", 9, alignment=TA_RIGHT, leading=14)


def P(t, st=CELL):
    return Paragraph(t, st)


def hl(t):
    """黄色マーカー（数字・成果の強調）"""
    return f'<font backColor="#ffe9a8"><b>{t}</b></font>'


def _photo_cell(width_mm=30, height_mm=40, label="写真貼付"):
    """証明写真セルを返す。`input/assets/photo.jpg` があれば実際に画像を埋め込み、
    無ければ従来通りのプレースホルダー枠を表示する。

    ⚠️ 2026-08-07修正: 従来このセルはコード上ハードコードでプレースホルダーの
    テキストボックスしか作らず、`reportlab.platypus.Image`を一度も使っていなかった。
    `input/README.md`・`documents/PROMPT.md`・`input/profile/01_基本情報.md`はいずれも
    「（写真を）置けば履歴書に自動で埋め込まれる」と説明していたが、**実装が存在せず、
    実際には機能していなかった**（fail-loudのassertでは検出できない種類の欠落——
    md側の見出し構成の問題ではなく、コードが最初から実装していない機能だったため）。
    本人が証明写真を用意したタイミングで実際にPDF化を試すまで気づかれなかった。
    """
    if os.path.exists(PHOTO_PATH):
        content = Image(PHOTO_PATH, width=width_mm * mm, height=height_mm * mm)
        pad = 0
    else:
        content = P(f"{label}<br/>{width_mm}mm×{height_mm}mm",
                    S("ph", 7.5, alignment=TA_CENTER, textColor=colors.HexColor("#999999")))
        pad = 2
    t = Table([[content]], colWidths=[width_mm * mm], rowHeights=[height_mm * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#aaaaaa")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                           ("LEFTPADDING", (0, 0), (-1, -1), pad),
                           ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                           ("TOPPADDING", (0, 0), (-1, -1), pad),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), pad)]))
    return t


# ============================================================ md 読み込み・パース
# documents/output/{接尾辞}/md/ を単一の情報源（single source of truth）とする。
# ここで md を構造化データに変換し、build_rirekisho / build_shokumu はそのデータを
# 流し込むだけにする（文言は一切変更しない。表示ロジック・スタイルのみ担当）。
import re as _re

# ⚠️ 2026-08-07: ファイル名の接尾辞ハードコードを解消（BACKLOG.md項目1、複数応募先対応）。
# 従来は "ExampleCo_ExampleRole" が RIREKISHO_MD 等の定数に直接埋め込まれており、他社の接尾辞では
# 動かなかった。`_md_paths(suffix)` に組み立てロジックを1箇所へ集約し、接尾辞は
# `documents/output/{接尾辞}/md/` に実在するファイルから自動検出する（`_discover_suffixes()`）。
# ⚠️ BACKLOG.md項目1が提案していた案（input/apply/07_応募先.mdから接尾辞を読み取る）ではなく
# 実在ファイルからの自動検出にした理由: 当時`07_応募先.md`は応募先を切り替えるたびに内容が
# 上書きされる単一の作業ファイルであり（過去の応募先の接尾辞情報が残っている保証がない）、
# 複数応募先が同時に`documents/output/{接尾辞}/md/`に存在する状態（今回のExamplePartner追加のような場面）を
# 正しく扱えない。生成済みファイルそのものを単一の情報源にする方が、設定と実体がズレるリスクが無い。
# ⚠️ 2026-08-09追記: `07_応募先.md`は`input/companies/{接尾辞}/07_応募先.md`として企業ごとに
# 分離されたため、当時の「単一の作業ファイル」という問題自体は解消済み。ただし本関数の設計
# （生成済みファイルからの自動検出）は依然として妥当なため変更しない——`input/`はあくまで
# 人手+LLMがdocuments/へ取捨選択する際の入力であり、build_pdf.py自体は`documents/output/{接尾辞}/md/`
# だけを見る、という役割分担の原則には変わりが無いため。
def _md_paths(suffix):
    """接尾辞（例: "ExampleCo_ExampleRole"）から4書類のmdパスを組み立てる。
    ファイル名の組み立てロジックはここに集約——他社対応時に触る場所はここだけでよい。"""
    md_dir = _out_dir(suffix, "md")
    return dict(
        rirekisho=os.path.join(md_dir, f"履歴書_{suffix}_ja.md"),
        shokumu=os.path.join(md_dir, f"職務経歴書_{suffix}_ja.md"),
        resume_en=os.path.join(md_dir, f"Resume_{suffix}_en.md"),
        rirekisho_en=os.path.join(md_dir, f"履歴書_{suffix}_en.md"),
    )


def _discover_suffixes():
    """documents/output/{接尾辞}/md/ に実在する4種のファイル名パターンから接尾辞を自動検出する。
    4パターンのいずれかにでも存在すれば拾う（英文レジュメのみ先行、等の状態にも対応するため）。"""
    patterns = [
        ("履歴書_*_ja.md", r"^履歴書_(.+)_ja\.md$"),
        ("職務経歴書_*_ja.md", r"^職務経歴書_(.+)_ja\.md$"),
        ("Resume_*_en.md", r"^Resume_(.+)_en\.md$"),
        ("履歴書_*_en.md", r"^履歴書_(.+)_en\.md$"),
    ]
    suffixes = set()
    for name_pat, name_re in patterns:
        # documents/output/{接尾辞}/md/ 配下を走査する（2026-08-10、応募先別フォルダ化）
        for p in glob.glob(os.path.join(OUT, "*", "md", name_pat)):
            m = _re.match(name_re, os.path.basename(p))
            if not m:
                continue
            from_name = m.group(1)
            from_dir = os.path.basename(os.path.dirname(os.path.dirname(p)))
            # ⚠️ fail-loud: フォルダ名とファイル名の接尾辞が食い違っていたら止める。
            # 応募先フォルダに他社のファイルを置いてしまう事故を、静かに通さないため。
            if from_name != from_dir:
                raise RuntimeError(
                    f"接尾辞の不一致: {os.path.relpath(p, BASE)}\n"
                    f"  フォルダ名は '{from_dir}' だが、ファイル名の接尾辞は '{from_name}'。\n"
                    f"  → documents/output/{{接尾辞}}/md/ の配下には、"
                    f"そのフォルダ名と同じ接尾辞のファイルだけを置いてください。")
            suffixes.add(from_name)
    return sorted(suffixes)


def _read_md(path):
    return open(path, encoding="utf-8").read()


def _split_h2(text):
    """`## 見出し` で分割し {見出し: 本文} を返す。"""
    parts = _re.split(r"^## (.+)$", text, flags=_re.M)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}


def _extract_date(text):
    """先頭部分（最初の `## `より前）にある「YYYY年M月D日現在」を取り出す。"""
    head = _re.split(r"^## ", text, maxsplit=1, flags=_re.M)[0]
    m = _re.search(r"\d{4}年\d{1,2}月\d{1,2}日現在", head)
    return m.group(0) if m else None


def _extract_date_en(text):
    """英語版履歴書の先頭（最初の `## `より前）にある英語表記の日付（例: "August 7, 2026"）
    を取り出す。_extract_date()は和暦「YYYY年M月D日現在」形式専用のため、英語版には
    このヘルパーを別途使う（2026-08-07追加）。"""
    head = _re.split(r"^## ", text, maxsplit=1, flags=_re.M)[0]
    m = _re.search(r"[A-Z][a-z]+ \d{1,2}, \d{4}", head)
    return m.group(0) if m else None


def _split_h3(text):
    parts = _re.split(r"^### (.+)$", text, flags=_re.M)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]


def _split_h4(text):
    parts = _re.split(r"^#### (.+)$", text, flags=_re.M)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]


def _table_rows(block):
    """`| a | b | ... |` 形式の表の全行（ヘッダー含む・区切り行は除く）を返す。"""
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(_re.fullmatch(r":?-{1,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows


def _bullets(block):
    """`- key: value` 形式の箇条書きを (key, value) のリストで返す。"""
    out = []
    for line in block.splitlines():
        m = _re.match(r"^-\s*([^:：]+)[:：]\s*(.+)$", line.strip())
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def _plain_bullets(block):
    """`- text` 形式の箇条書き（key: value 分割はしない）をリストで返す。英文レジュメ用。"""
    return [line.strip()[2:].strip() for line in block.splitlines() if line.strip().startswith("- ")]


def _paragraphs(block):
    """空行区切りの段落を返す（見出し・表・箇条書き・区切り線・注記行は除外）。"""
    paras, cur = [], []
    for line in block.splitlines():
        s = line.strip()
        if not s:
            if cur:
                paras.append(" ".join(cur)); cur = []
            continue
        if s.startswith(("#", "|", "-", ">", "※", "---")):
            continue
        cur.append(s)
    if cur:
        paras.append(" ".join(cur))
    return paras


def _esc(text):
    """reportlab の Paragraph は疑似 XML として解釈するため、& < > をエスケープする
    （md 本文には "P&L" のような生の "&" が含まれるため必須）。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mark_star(text):
    return _re.sub(r"★", '<font color="#cc0000"><b>★</b></font>', text)


def _star(text):
    """★ を赤字強調に変換する（両文書共通）。text は未エスケープの生テキスト。"""
    return _mark_star(_esc(text))


def _bold(text):
    """**text** を <b> に変換する（履歴書向け。JIS 様式なので黄色マーカーは使わない）。"""
    t = _esc(text)
    t = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return _mark_star(t)


def _bold_hl(text):
    """**text** を hl() の黄色マーカーに変換する（内部レビュー用）。
    2026-08-05: 提出版PDFでは黄色ハイライトを使わない方針（documents/PROMPT.md参照）に
    伴い、build_shokumu() は本関数ではなく _bold() を呼ぶよう変更済み。
    本関数とhl()自体は削除せず残す——内部レビュー用に色付きで出したい場面があれば、
    build_shokumu() 内の該当箇所を _bold_hl() に戻すだけで復活させられるようにするため。"""
    t = _esc(text)
    t = _re.sub(r"\*\*(.+?)\*\*", lambda m: hl(m.group(1)), t)
    return _mark_star(t)


def _strip_bold(text):
    """**text** の記号だけを外し、タグは付けない（表の見出しセルなど、元々太字スタイルの
    セルに使う。二重に強調しないようにするため）。"""
    return _re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def _strip_trailing_rule(text):
    """段落抽出時に紛れ込む末尾の水平線（---）を取り除く。"""
    return _re.sub(r"\n*-{3,}\s*$", "", text.strip()).strip()


# ============================================================ 見出し → 内部key 対応表・fail-loud化
# 2026-08-06追加（ARCHITECTURE.md／LESSONS.md教訓22・24）。
#
# 目的: このパーサーは md の見出し名に文字列一致で依存している。従来は
#   ①期待する見出しが無い → secs["X"] のKeyErrorで（分かりにくいメッセージのまま）クラッシュ
#   ②md に新しい見出しを追加したがコードが対応していない → クラッシュせず、静かに描画から漏れる
# という非対称な挙動だった。②が2026-08-05に実際発生しかけた事故そのもの（「対応中の上位資格」
# セクションの取りこぼし）。以下の assert は①のメッセージを分かりやすくし、②を①と同じ
# 「即座に落ちる」失敗に変える（沈黙の失敗を無くす）。
#
# md の見出し名を変更・追加する場合は、この対応表と load_*() 内の参照箇所を同時に変更すること。

RIREKISHO_H2 = {"基本情報", "学歴・職歴", "免許・資格", "志望の動機・自己PR", "通勤・扶養家族",
                "賞罰・健康状態", "本人希望記入欄"}
# 「通勤・扶養家族」は今回のfail-loud化の初回実行で実際に検出された欠落（2026-08-06）。
# md には存在するが、これまでload_rirekisho()/build_rirekisho()のどちらにも一切コードが
# 無く、履歴書PDFから最寄駅・通勤時間・扶養家族数・配偶者情報が完全に欠落していた。
# このセクションは本セットの見直し作業で新たに発見したため、合わせて修正した
# （履歴書_ja.pdf自体はJIS履歴書として2026-08-06時点で未提出。詳細は本人への報告参照）。
# 「賞罰・健康状態」は2026-08-07追加（本人提示のWord履歴書との突き合わせを機に、
# JIS標準項目として新設。本人同意済み）。

# JIS履歴書の英訳版（ATS形式のResume_en.mdとは別物）。ファイル名は_md_paths()で組み立てる。
RIREKISHO_EN_H2 = {"Personal Information", "Education / Work History", "Licenses / Qualifications",
                   "Motivation / Self-PR", "Commute / Dependents", "Disciplinary Record / Health",
                   "Personal Requests"}
RIREKISHO_GAKU_SHOKU_H3 = {"学歴", "職歴"}

SHOKUMU_H2 = {"職務要約", "活かせる経験・知識・スキル", "職務経歴", "マネジメント経験", "語学",
             "自己PR", "テクニカルスキル", "保有資格"}
# 保有資格の直下(H3)の分類ルール。
# ⚠️ 2026-08-09（ARCHITECTURE.md 2-9 f への対応）: 従来はここに
#     SHOKUMU_CERT_H3_PREFIX_REQUIRED = ["ExampleCloud 認定", "Microsoft 認定"]
# という**ベンダー名のリテラル**を持ち、load_shokumu()が[0]=ExampleCloud・[1]=Microsoftという
# 「並び順」にまで依存していた。これは本人が保有する認定のベンダー構成（＝3層モデルの①本人データ）を、
# 会社非依存であるべきscripts/層に埋め込んでいる状態であり、ベンダーが増減・改称した時点で破綻する。
# 現在は**ベンダー名をコードに一切持たず**、見出しの「かたち」だけで仕分ける:
#   1. 「主要認定」          … 完全一致・必須（先頭の一覧表）
#   2. 「対応中の上位資格」  … prefix一致・任意（取得済みと混ぜてはいけない別区分）
#   3. 上記以外で「認定」を含む見出し … ベンダー別認定セクション（1件以上必須・md出現順を保持）
#   4. どれにも当たらない見出し       … fail-loudで停止（取りこぼし事故の再発防止）
SHOKUMU_CERT_H3_EXACT_REQUIRED = {"主要認定"}
SHOKUMU_CERT_H3_PREFIX_OPTIONAL = ["対応中の上位資格"]
SHOKUMU_CERT_H3_VENDOR_MARK = "認定"   # ベンダー別セクションの識別に使う語（ベンダー名そのものではない）

RESUME_EN_H2 = {"Professional Summary", "Core Competencies", "Professional Experience",
                "Certifications", "Education"}


def _assert_h2_set(secs, expected, label):
    """secs（_split_h2の戻り値）のキー集合が期待セットと過不足なく一致するかを検証する。
    不足（期待したのに無い）・余剰（mdにあるのにコードが知らない）の両方を検出し、
    見つかり次第すぐに例外で停止する（fail-loud）。"""
    got = set(secs.keys())
    missing = expected - got
    extra = got - expected
    if missing:
        raise RuntimeError(f"{label}: 期待する見出し(##)が見つかりません: {sorted(missing)}"
                           f"\n  → 見出し名が変更・削除されていないか確認してください。")
    if extra:
        raise RuntimeError(f"{label}: 未知の見出し(##)が見つかりました: {sorted(extra)}"
                           f"\n  → 新しいセクションを追加したなら、build_pdf.py側の対応表(RIREKISHO_H2等)と"
                           f"load_*()の両方を更新してください（教訓22・24）。")


def _assert_h3_set(sub, expected, label):
    """_split_h3の戻り値（dict化済み）のキー集合を厳密一致で検証する（学歴・職歴等、
    見出し名が固定で列挙可能なケース向け）。"""
    got = set(sub.keys())
    missing = expected - got
    extra = got - expected
    if missing:
        raise RuntimeError(f"{label}: 期待する見出し(###)が見つかりません: {sorted(missing)}")
    if extra:
        raise RuntimeError(f"{label}: 未知の見出し(###)が見つかりました: {sorted(extra)}"
                           f"\n  → build_pdf.py側の対応表とload_*()を更新してください（教訓22・24）。")


def _classify_cert_subs(cert_subs, label="職務経歴書/保有資格"):
    """保有資格直下(H3)を「主要認定（完全一致・必須）」「ベンダー別認定（『認定』を含む見出し・
    1件以上必須）」「対応中の上位資格（prefix一致・任意）」に仕分ける。
    どれにも当てはまらない見出しは fail-loud の対象——これが「対応中の上位資格」取りこぼし事故の
    再発防止そのもの。

    ⚠️ ベンダー名（ExampleCloud / Microsoft 等）はコードに一切持たない。md にベンダーが増えても
    改称されても、このコードは変更不要（ARCHITECTURE.md 2-9 f への対応、2026-08-09）。

    戻り値: (ベンダー別見出しのリスト〔md出現順〕, 対応中の上位資格の見出し or None)
    """
    got = list(cert_subs.keys())   # dict は挿入順＝md の出現順を保持する
    consumed = set()

    missing = SHOKUMU_CERT_H3_EXACT_REQUIRED - set(got)
    consumed |= SHOKUMU_CERT_H3_EXACT_REQUIRED & set(got)

    learning = [k for k in got
                if any(k.startswith(p) for p in SHOKUMU_CERT_H3_PREFIX_OPTIONAL)]
    consumed |= set(learning)

    vendors = [k for k in got
               if k not in consumed and SHOKUMU_CERT_H3_VENDOR_MARK in k]
    consumed |= set(vendors)
    if not vendors:
        missing.add(f"...{SHOKUMU_CERT_H3_VENDOR_MARK}（ベンダー別認定セクション）")

    if missing:
        raise RuntimeError(f"{label}: 必須の見出しが見つかりません: {sorted(missing)}")
    unknown = set(got) - consumed
    if unknown:
        raise RuntimeError(f"{label}: 未知の見出しが見つかりました: {sorted(unknown)}"
                           f"\n  → 新しい資格区分を追加したなら、SHOKUMU_CERT_H3_*（build_pdf.py冒頭）と"
                           f"load_shokumu()の両方を更新してください（教訓22・24）。")
    return vendors, (learning[0] if learning else None)


def _vendor_short(heading):
    """「ExampleCloud 認定（計3件）」→「ExampleCloud」。ベンダー別グループのラベル接頭辞を、
    コード側のリテラルではなく**見出しそのもの**から導く（ARCHITECTURE.md 2-9 f）。"""
    return _re.split(rf"\s*{SHOKUMU_CERT_H3_VENDOR_MARK}", heading, maxsplit=1)[0].strip() or heading


def _cert_vendor_items(heading, body_raw):
    """1つのベンダー別認定セクションを、描画用の (ラベル, 本文) のリストに変換する。
    セクション内に `**小見出し**` があればそれごとに分割し「{ベンダー} — {小見出し}」を
    ラベルにする。無ければセクション全体を1件として、見出しをそのままラベルにする。
    ⚠️ 分岐の基準は**中身のかたち**であり、ベンダー名ではない。"""
    raw = body_raw.strip()
    groups_raw = _re.findall(r"\*\*(.+?)\*\*\n\n(.+?)(?=\n\n\*\*|\Z)", raw + "\n\n**", _re.S)
    if groups_raw:
        short = _vendor_short(heading)
        return [(f"{short} — {g.strip()}", _strip_cert_tail(b)) for g, b in groups_raw]
    return [(heading, _strip_cert_tail(raw))]


def _strip_cert_tail(body):
    """区切り線と、md 末尾の「以上」（ファイル終端の区切りであり本文ではない）を落とす。
    「以上」は build_shokumu() が別途固定で描画するため、残すと二重表示になる。"""
    return _re.sub(r"\n*以上\s*$", "", _strip_trailing_rule(body).strip()).strip()


def load_rirekisho(suffix):
    raw = _read_md(_md_paths(suffix)["rirekisho"])
    secs = _split_h2(raw)
    _assert_h2_set(secs, RIREKISHO_H2, "履歴書")
    date = _extract_date(raw)

    basic_rows = _table_rows(secs["基本情報"])[1:]  # ヘッダー行を除く
    furigana = [v for k, v in basic_rows if k == "ふりがな"]
    by_label = {k: v for k, v in basic_rows if k != "ふりがな"}
    basic = dict(
        name_furigana=furigana[0], addr_furigana=furigana[1],
        name=by_label["氏名"], dob=by_label["生年月日"], gender=by_label["性別"],
        nationality=by_label["国籍・在留資格"], email=by_label["メール"],
        address=by_label["現住所"], phone=by_label["電話"], contact=by_label["連絡先"],
    )

    edu = dict(_split_h3(secs["学歴・職歴"]))
    _assert_h3_set(edu, RIREKISHO_GAKU_SHOKU_H3, "履歴書/学歴・職歴")
    gaku_rows = _table_rows(edu["学歴"])[1:]
    shoku_rows = _table_rows(edu["職歴"])[1:]
    lic_rows = _table_rows(secs["免許・資格"])[1:]
    # ⚠️ 2026-08-10: 従来は _re.search で「最初の1行だけ」を拾っており、※が複数行あると
    # 2行目以降がPDFから静かに消えていた（ExamplePartnerの履歴書で実際に3行中2行が欠落）。
    # findall に変更し、全ての※行をそれぞれ1行として描画する（※が1行のときの出力は従来と同一）。
    lic_notes = [x.strip() for x in _re.findall(r"^※\s*(.+)$", secs["免許・資格"], _re.M)]
    pr_paras = _paragraphs(secs["志望の動機・自己PR"])
    commute = _bullets(secs["通勤・扶養家族"])
    shobatsu = _bullets(secs["賞罰・健康状態"])
    hope = _bullets(secs["本人希望記入欄"])

    return dict(date=date, basic=basic, gaku=gaku_rows, shoku=shoku_rows, lic=lic_rows,
                lic_notes=lic_notes, pr=pr_paras, commute=commute, shobatsu=shobatsu, hope=hope)


def load_shokumu(suffix):
    raw = _read_md(_md_paths(suffix)["shokumu"])
    secs = _split_h2(raw)
    _assert_h2_set(secs, SHOKUMU_H2, "職務経歴書")
    date = _extract_date(raw)

    summary = _paragraphs(secs["職務要約"])

    skill_items = _re.findall(r"\*\*(.+?)\*\*\n(.+?)(?=\n\*\*|\Z)",
                              secs["活かせる経験・知識・スキル"], _re.S)
    skill_items = [(h.strip(), _strip_trailing_rule(b)) for h, b in skill_items]

    companies = []
    for cname, cbody in _split_h3(secs["職務経歴"]):
        # 会社の見出し直下・最初の #### 案件より前にある本文だけを対象に bullets／note を取る
        head_block = _re.split(r"^#### ", cbody, maxsplit=1, flags=_re.M)[0]
        bullets = _bullets(head_block)
        note = None
        m = _re.search(r"^※\s*(.+)$", head_block, _re.M)
        if m:
            note = m.group(1).strip()
        cases = []
        for casename, casebody in _split_h4(cbody):
            if "提案対象製品:" in casebody:
                main_block, vendor_block = casebody.split("提案対象製品:", 1)
                main_rows = _table_rows(main_block)[1:]
                vendor_rows = _table_rows(vendor_block)
            else:
                main_rows = _table_rows(casebody)[1:]
                vendor_rows = None
            cases.append(dict(name=casename, rows=main_rows, vendor=vendor_rows))
        companies.append(dict(name=cname, bullets=bullets, cases=cases, note=note))

    if not companies:
        raise RuntimeError("職務経歴書/職務経歴: 会社セクションが1件もありません")

    tech_rows = _table_rows(secs["テクニカルスキル"])[1:]
    mgmt = [l.strip()[2:] for l in secs["マネジメント経験"].splitlines() if l.strip().startswith("- ")]
    lang = [l.strip()[2:] for l in secs["語学"].splitlines() if l.strip().startswith("- ")]

    cert_subs = dict(_split_h3(secs["保有資格"]))
    vendor_headings, learning_heading = _classify_cert_subs(cert_subs)
    cert_main_rows = _table_rows(cert_subs["主要認定"])[1:]

    # ⚠️ 2026-08-09（ARCHITECTURE.md 2-9 f）: 従来はここで
    #     sn_heading = [...startswith(SHOKUMU_CERT_H3_PREFIX_REQUIRED[0])][0]   # = ExampleCloud
    #     ms_heading = [...startswith(SHOKUMU_CERT_H3_PREFIX_REQUIRED[1])][0]   # = Microsoft
    # とベンダーを名指し＋位置決め打ちで取り出し、ラベルにも "ExampleCloud — " をリテラルで
    # 書いていた。ベンダーが増減・改称した瞬間に IndexError か無言の欠落になる構造だったため、
    # md出現順のまま総なめする形に置き換えた。**コード側にベンダー名は残っていない。**
    # 先頭セクションの見出しが H4 見出しとして描画され、以降は各セクションが
    # インラインのラベル付きブロックになる（描画側の挙動は従来と同一）。
    cert_vendor_heading = vendor_headings[0]
    cert_vendor_items = []
    for h in vendor_headings:
        cert_vendor_items += _cert_vendor_items(h, cert_subs[h])

    # 対応中の上位資格（結果待ち・受験予定）（CRMA・CTA等、「取得済み」と誤読されないよう主要認定・
    # ベンダー別認定とは別区分でレンダリングする。2026-08-05追加。cert_subsに拾われるだけで
    # 終わらせず、明示的にdata dictへ渡してbuild_shokumu()側で描画すること——教訓22の再発防止）
    learning_body = _strip_cert_tail(cert_subs[learning_heading]) if learning_heading else None

    pr_paras = _paragraphs(secs["自己PR"])

    name_match = _re.search(r"^氏名\s*[:：]\s*(.+)$", raw, _re.M)
    name = name_match.group(1).strip() if name_match else ""

    return dict(date=date, name=name, summary=summary, skill_items=skill_items, companies=companies,
                tech_rows=tech_rows, mgmt=mgmt, lang=lang,
                cert_main_rows=cert_main_rows,
                cert_vendor_heading=cert_vendor_heading, cert_vendor_items=cert_vendor_items,
                learning_heading=learning_heading, learning_body=learning_body,
                pr=pr_paras)


def load_resume_en(suffix):
    raw = _read_md(_md_paths(suffix)["resume_en"])

    # `## ` より前（# 氏名 / 連絡先 / --- ）を見出しブロックとして個別に読む。
    head = _re.split(r"^## ", raw, maxsplit=1, flags=_re.M)[0]
    head_lines = [l.strip() for l in head.splitlines() if l.strip() and l.strip() != "---"]
    name = head_lines[0].lstrip("#").strip()
    contact = head_lines[1] if len(head_lines) > 1 else ""

    secs = _split_h2(raw)
    _assert_h2_set(secs, RESUME_EN_H2, "英文レジュメ")
    summary = _paragraphs(secs["Professional Summary"])[0]

    competencies, languages = _paragraphs(secs["Core Competencies"])

    companies = []
    for cname, cbody in _split_h3(secs["Professional Experience"]):
        paras = _paragraphs(cbody)
        role = paras[0]
        context = paras[1] if len(paras) > 1 else None
        bullets = _plain_bullets(cbody)
        companies.append(dict(name=cname, role=role, context=context, bullets=bullets))

    certs = _paragraphs(secs["Certifications"])
    education = _paragraphs(secs["Education"])

    return dict(name=name, contact=contact, summary=summary, competencies=competencies,
                languages=languages, companies=companies, certs=certs, education=education)


def load_rirekisho_en(suffix):
    """JIS履歴書の英訳版を読み込む。load_rirekisho()と同じ構造・同じ
    ヘルパー関数（_split_h2/_table_rows/_bullets/_paragraphs）を使うが、見出し名・
    フィールド名が英語であるため、対応表（RIREKISHO_EN_H2）・辞書キーは別に持つ。"""
    raw = _read_md(_md_paths(suffix)["rirekisho_en"])
    secs = _split_h2(raw)
    _assert_h2_set(secs, RIREKISHO_EN_H2, "履歴書(英語版)")
    date = _extract_date_en(raw)

    basic_rows = _table_rows(secs["Personal Information"])[1:]  # ヘッダー行を除く
    basic = {k: v for k, v in basic_rows}

    edu = dict(_split_h3(secs["Education / Work History"]))
    _assert_h3_set(edu, {"Education", "Work History"}, "履歴書(英語版)/Education-WorkHistory")
    gaku_rows = _table_rows(edu["Education"])[1:]
    shoku_rows = _table_rows(edu["Work History"])[1:]

    lic_rows = _table_rows(secs["Licenses / Qualifications"])[1:]
    # ⚠️ 2026-08-10: 日本語版と同じ理由で findall に変更（詳細は load_rirekisho 側のコメント）。
    lic_notes = [x.strip() for x in _re.findall(r"^※\s*(.+)$", secs["Licenses / Qualifications"], _re.M)]

    pr_paras = _paragraphs(secs["Motivation / Self-PR"])
    commute = _bullets(secs["Commute / Dependents"])
    shobatsu = _bullets(secs["Disciplinary Record / Health"])
    hope = _bullets(secs["Personal Requests"])

    return dict(date=date, basic=basic, gaku=gaku_rows, shoku=shoku_rows, lic=lic_rows,
                lic_notes=lic_notes, pr=pr_paras, commute=commute, shobatsu=shobatsu, hope=hope)


def doc_template(path, top=13 * mm, bottom=13 * mm, left=12 * mm, right=12 * mm, title="",
                 footer_font="JP", author=""):
    d = BaseDocTemplate(path, pagesize=A4, topMargin=top, bottomMargin=bottom,
                        leftMargin=left, rightMargin=right, title=title, author=author)
    w = A4[0] - left - right
    h = A4[1] - top - bottom
    frame = Frame(left, bottom, w, h, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0, id="f")

    def footer(canvas, docu):
        canvas.saveState()
        canvas.setFont(footer_font, 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(A4[0] / 2, 7 * mm, f"- {docu.page} -")
        canvas.restoreState()

    d.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=footer)])
    return d, w


# ================================================================== 履歴書
def build_rirekisho(path, suffix):
    data = load_rirekisho(suffix)
    b = data["basic"]
    doc, W = doc_template(path, title=f"履歴書 {b['name']}", author=b["name"])
    st = []

    head = Table([[Paragraph("履 歴 書", ParagraphStyle("t", fontName="JPB", fontSize=17,
                                                       leading=22, textColor=INK)),
                   Paragraph(data["date"], META)]],
                 colWidths=[W * 0.6, W * 0.4])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    st += [head, Spacer(1, 3 * mm)]

    # --- 基本情報
    photo = _photo_cell(label="写真貼付")

    c = [29 * mm, 49 * mm, 14 * mm, 24 * mm, 34 * mm]
    c[4] = W - sum(c[:4])
    data_rows = [
        [P("ふりがな", CELLB), P(_bold(b["name_furigana"])), "", "", photo],
        [P("氏名", CELLB), P(_bold(b["name"]), S("nm", 13, font="JPB")), "", "", ""],
        [P("生年月日", CELLB), P(_bold(b["dob"])), P("性別", CELLB), P(_bold(b["gender"])), ""],
        [P("国籍・在留資格", CELLB), P(_bold(b["nationality"])), "", "", ""],
        [P("メール", CELLB), P(_bold(b["email"])), "", "", ""],
        [P("ふりがな", CELLB), P(_bold(b["addr_furigana"])), "", "", ""],
        [P("現住所", CELLB), P(_bold(b["address"])), "", "", ""],
        [P("電話", CELLB), P(_bold(b["phone"])), P("連絡先", CELLB), P(_bold(b["contact"])), ""],
    ]
    t = Table(data_rows, colWidths=c)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, LINE),
        ("BACKGROUND", (0, 0), (0, -1), HEAD),
        ("BACKGROUND", (2, 2), (2, 2), HEAD),
        ("BACKGROUND", (2, 7), (2, 7), HEAD),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
        ("SPAN", (1, 0), (3, 0)), ("SPAN", (1, 1), (3, 1)),
        ("SPAN", (1, 3), (3, 3)), ("SPAN", (1, 4), (3, 4)),
        ("SPAN", (4, 0), (4, 4)),
        ("SPAN", (1, 5), (4, 5)), ("SPAN", (1, 6), (4, 6)),
        ("SPAN", (3, 7), (4, 7)),
        ("ALIGN", (4, 0), (4, 4), "CENTER"),
        ("TOPPADDING", (4, 0), (4, 4), 2 * mm),
    ]))
    st += [t, Spacer(1, 3 * mm)]

    # --- 学歴・職歴
    cw = [13 * mm, 10 * mm]
    cw.append(W - sum(cw))
    rows = [[P("年", CELLC), P("月", CELLC), P("学歴・職歴", CELLB)],
            [P("学　歴", S("ctr", 9.5, font="JPB", alignment=TA_CENTER)), "", ""]]

    def cell3(y, m, s):
        return [P(_star(y), CELLC), P(_star(m), CELLC), P(_bold(s), CELLR if s == "以上" else CELL)]

    for y, m, s in data["gaku"]:
        rows.append(cell3(y, m, s))
    center_rows = [1]
    rows.append([P("職　歴", S("ctr2", 9.5, font="JPB", alignment=TA_CENTER)), "", ""])
    center_rows.append(len(rows) - 1)
    for y, m, s in data["shoku"]:
        rows.append(cell3(y, m, s))

    t2 = Table(rows, colWidths=cw, repeatRows=1)
    sty = [("GRID", (0, 0), (-1, -1), 0.6, LINE),
           ("BACKGROUND", (0, 0), (-1, 0), HEAD),
           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
           ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
           ("TOPPADDING", (0, 0), (-1, -1), 1.3 * mm),
           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3 * mm)]
    for r in center_rows:
        sty += [("SPAN", (0, r), (2, r)), ("BACKGROUND", (0, r), (2, r), colors.HexColor("#fafafa"))]
    t2.setStyle(TableStyle(sty))
    st += [t2, Spacer(1, 3 * mm)]

    # --- 免許・資格
    rows3 = [[P("年", CELLC), P("月", CELLC), P("免許・資格", CELLB)]]
    for y, m, s in data["lic"]:
        rows3.append(cell3(y, m, s))
    t3 = Table(rows3, colWidths=cw, repeatRows=1)
    t3.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                            ("BACKGROUND", (0, 0), (-1, 0), HEAD),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.3 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3 * mm)]))
    st += [t3, Spacer(1, 1.5 * mm)]
    for _n in data["lic_notes"]:
        st += [P(f"※ {_bold(_n)}", SMALL)]
    st += [Spacer(1, 3 * mm)]

    # --- 志望の動機・自己PR
    pr = "<br/><br/>".join(_bold(p) for p in data["pr"])
    t4 = Table([[P("志望の動機・自己PR", CELLB)], [P(pr, BODY)]], colWidths=[W])
    t4.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                            ("BACKGROUND", (0, 0), (0, 0), HEAD),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm)]))
    st += [t4, Spacer(1, 3 * mm)]

    # --- 通勤・扶養家族（2026-08-06追加。fail-loud化の初回実行で発覚した欠落の修正——
    # 従来このセクションはmdに存在するのに描画コードが無く、履歴書PDFから完全に欠落していた）
    cw6 = [42 * mm, W - 42 * mm]
    rows6 = [[P(k, CELLB), P(_bold(v))] for k, v in data["commute"]]
    t6 = Table(rows6, colWidths=cw6)
    t6.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                            ("BACKGROUND", (0, 0), (0, -1), HEAD),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm)]))
    st += [t6, Spacer(1, 3 * mm)]

    # --- 賞罰・健康状態（2026-08-07追加。JIS標準項目、本人同意済み）
    cw6b = [42 * mm, W - 42 * mm]
    rows6b = [[P(k, CELLB), P(_bold(v))] for k, v in data["shobatsu"]]
    t6b = Table(rows6b, colWidths=cw6b)
    t6b.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                             ("BACKGROUND", (0, 0), (0, -1), HEAD),
                             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                             ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm)]))
    st += [t6b, Spacer(1, 3 * mm)]

    # --- 本人希望記入欄
    rows5 = [[P("本人希望記入欄", CELLB), ""]]
    for k, v in data["hope"]:
        rows5.append([P(k, CELLB), P(_bold(v))])
    t5 = Table(rows5, colWidths=[32 * mm, W - 32 * mm])
    t5.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                            ("BACKGROUND", (0, 0), (-1, 0), HEAD),
                            ("BACKGROUND", (0, 1), (0, -1), HEAD),
                            ("SPAN", (0, 0), (1, 0)),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm)]))
    st.append(t5)
    doc.build(st)
    return path


# ============================================================ 履歴書（英語版）
# JIS履歴書の構造・項目をそのまま維持した英訳版（2026-08-07追加）。ATS形式の
# build_resume_en()とは別物——写真・生年月日・通勤時間・扶養家族等、日本固有の
# 項目を一切削らない方針（本人指示）。build_rirekisho()とほぼ同じレイアウトを、
# 英語の静的ラベルで再構成する。
def build_rirekisho_en(path, suffix):
    data = load_rirekisho_en(suffix)
    b = data["basic"]
    doc, W = doc_template(path, title=f"Rirekisho (Japanese-Format CV) - {b['Name']}", author=b["Name"])
    st = []

    head = Table([[Paragraph("RIREKISHO", ParagraphStyle("t_en", fontName="JPB", fontSize=17,
                                                          leading=22, textColor=INK)),
                   Paragraph(data["date"], META)]],
                 colWidths=[W * 0.6, W * 0.4])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    st += [head, Spacer(1, 1 * mm),
           P("(Japanese-Format CV — English Translation)", SMALL), Spacer(1, 2 * mm)]

    # --- Personal Information（写真付き。日本語版と同じくフィールドを削らない）
    photo = _photo_cell(label="Photo")

    label_w = 46 * mm
    photo_w = 34 * mm
    info_w = W - label_w - photo_w
    basic_order = ["Furigana (reading)", "Name", "Date of Birth", "Gender",
                   "Nationality / Residence Status", "Furigana (address reading)",
                   "Current Address", "Phone", "Email", "Contact"]
    basic_rows_en = [[P(k, CELLB), P(_bold(b[k])), photo if i == 0 else ""]
                     for i, k in enumerate(basic_order)]
    t_en = Table(basic_rows_en, colWidths=[label_w, info_w, photo_w])
    sty_en = [("GRID", (0, 0), (1, -1), 0.6, LINE),
              ("BACKGROUND", (0, 0), (0, -1), HEAD),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
              ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
              ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
              ("SPAN", (2, 0), (2, len(basic_order) - 1)),
              ("ALIGN", (2, 0), (2, 0), "CENTER"),
              ("VALIGN", (2, 0), (2, 0), "TOP"),
              ("TOPPADDING", (2, 0), (2, 0), 2 * mm)]
    t_en.setStyle(TableStyle(sty_en))
    st += [t_en, Spacer(1, 3 * mm)]

    # --- Education / Work History
    # 2026-08-07修正: 日本語版と同じ13mm/10mmだと英語の"Year"/"Month"が折り返して
    # 見苦しくなっていた（実際にレンダリングして発覚）。英語見出しの幅に合わせて拡げる。
    cw = [15 * mm, 17 * mm]
    cw.append(W - sum(cw))
    rows = [[P("Year", CELLC), P("Month", CELLC), P("Education / Work History", CELLB)],
            [P("Education", S("ctr_en", 9.5, font="JPB", alignment=TA_CENTER)), "", ""]]

    def cell3_en(y, m, s):
        return [P(_star(y), CELLC), P(_star(m), CELLC),
               P(_bold(s), CELLR if s == "End of record" else CELL)]

    for y, m, s in data["gaku"]:
        rows.append(cell3_en(y, m, s))
    center_rows = [1]
    rows.append([P("Work History", S("ctr2_en", 9.5, font="JPB", alignment=TA_CENTER)), "", ""])
    center_rows.append(len(rows) - 1)
    for y, m, s in data["shoku"]:
        rows.append(cell3_en(y, m, s))

    t2 = Table(rows, colWidths=cw, repeatRows=1)
    sty = [("GRID", (0, 0), (-1, -1), 0.6, LINE),
           ("BACKGROUND", (0, 0), (-1, 0), HEAD),
           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
           ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
           ("TOPPADDING", (0, 0), (-1, -1), 1.3 * mm),
           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3 * mm)]
    for r in center_rows:
        sty += [("SPAN", (0, r), (2, r)), ("BACKGROUND", (0, r), (2, r), colors.HexColor("#fafafa"))]
    t2.setStyle(TableStyle(sty))
    st += [t2, Spacer(1, 3 * mm)]

    # --- Licenses / Qualifications
    rows3 = [[P("Year", CELLC), P("Month", CELLC), P("Licenses / Qualifications", CELLB)]]
    for y, m, s in data["lic"]:
        rows3.append(cell3_en(y, m, s))
    t3 = Table(rows3, colWidths=cw, repeatRows=1)
    t3.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                            ("BACKGROUND", (0, 0), (-1, 0), HEAD),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.3 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3 * mm)]))
    st += [t3, Spacer(1, 1.5 * mm)]
    for _n in data["lic_notes"]:
        st += [P(f"※ {_bold(_n)}", SMALL)]
    st += [Spacer(1, 3 * mm)]

    # --- Motivation / Self-PR
    pr = "<br/><br/>".join(_bold(p) for p in data["pr"])
    t4 = Table([[P("Motivation / Self-PR", CELLB)], [P(pr, BODY)]], colWidths=[W])
    t4.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                            ("BACKGROUND", (0, 0), (0, 0), HEAD),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm)]))
    st += [t4, Spacer(1, 3 * mm)]

    # --- Commute / Dependents
    cw6 = [55 * mm, W - 55 * mm]
    rows6 = [[P(k, CELLB), P(_bold(v))] for k, v in data["commute"]]
    t6 = Table(rows6, colWidths=cw6)
    t6.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                            ("BACKGROUND", (0, 0), (0, -1), HEAD),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm)]))
    st += [t6, Spacer(1, 3 * mm)]

    # --- Disciplinary Record / Health
    cw6b = [55 * mm, W - 55 * mm]
    rows6b = [[P(k, CELLB), P(_bold(v))] for k, v in data["shobatsu"]]
    t6b = Table(rows6b, colWidths=cw6b)
    t6b.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                             ("BACKGROUND", (0, 0), (0, -1), HEAD),
                             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                             ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm)]))
    st += [t6b, Spacer(1, 3 * mm)]

    # --- Personal Requests
    rows5 = [[P("Personal Requests", CELLB), ""]]
    for k, v in data["hope"]:
        rows5.append([P(k, CELLB), P(_bold(v))])
    t5 = Table(rows5, colWidths=[42 * mm, W - 42 * mm])
    t5.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, LINE),
                            ("BACKGROUND", (0, 0), (-1, 0), HEAD),
                            ("BACKGROUND", (0, 1), (0, -1), HEAD),
                            ("SPAN", (0, 0), (1, 0)),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm)]))
    st.append(t5)
    doc.build(st)
    return path


# ============================================================ 職務経歴書
def build_shokumu(path, suffix):
    data = load_shokumu(suffix)
    # 2026-08-04: 6→5ページ化のための組版調整（本文フォントサイズは不変）。
    # 英文レジュメ（build_resume_en）・履歴書（build_rirekisho）には一切影響しない
    # よう、余白・行間・パディング・スペーサーはすべてこの関数内のローカル値のみ変更する。
    doc, W = doc_template(path, top=11 * mm, bottom=11 * mm, left=11 * mm, right=11 * mm,
                          title=f"職務経歴書 {data['name']}", author=data["name"])
    st = []
    # 行間をやや詰める（1.56倍 → 約1.42倍）。フォントサイズ自体は変えない。
    BODY = S("body_sk", 9.5, leading=9.5 * 1.42)
    CELL = S("cell_sk", 9, leading=9 * 1.42)
    CELLB = S("cellb_sk", 9, font="JPB", leading=9 * 1.42)
    SMALL = S("small_sk", 8.3, leading=11)
    H2 = S("h2", 11.5, font="JPB", leading=15)
    H3 = S("h3", 10.5, font="JPB", leading=14)
    H4 = S("h4", 10, font="JPB", leading=13)

    def band(text, keep_with=None):
        """セクション見出しバナー。2026-08-05: 見出しの孤立（ページ最下部に見出しだけが
        取り残され、本文が次ページに送られる）を防ぐため、`keep_with` に見出し直後の
        「最初の小さな要素」（Flowable、またはFlowableのリスト）を渡すと、見出しと
        まとめてKeepTogetherで包む。⚠️ ここに渡すのは段落1つ・項目1つ程度に留めること
        （テーブル全体など大きな要素を渡すと、1ページに収まらない場合に大きな空白を
        生む副作用があるため）。呼び出し側は「最初の要素だけ」を渡し、残りは従来通り
        個別に`st`へ追加する。"""
        t = Table([[Paragraph(text, H2)]], colWidths=[W])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BANNER),
                               ("LINEBEFORE", (0, 0), (0, -1), 1.4, ACC),
                               ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.1 * mm),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1 * mm)]))
        head = [Spacer(1, 2.2 * mm), t, Spacer(1, 1.6 * mm)]
        if keep_with is None:
            return head
        extra = keep_with if isinstance(keep_with, list) else [keep_with]
        return [KeepTogether(head + extra)]

    def _kv_style():
        return TableStyle([("GRID", (0, 0), (-1, -1), 0.5, SOFT),
                           ("BACKGROUND", (0, 0), (0, -1), HEAD2),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.1 * mm),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1 * mm)])

    def kv(rows, label_w=23 * mm):
        data = [[P(_strip_bold(k), CELLB), P(_bold(v))] for k, v in rows]
        t = Table(data, colWidths=[label_w, W - label_w])
        t.setStyle(_kv_style())
        return t

    def kv_split(rows, label_w=23 * mm):
        """先頭1行だけの小テーブルと、残り行の続きテーブルを別々に返す（2026-08-05追加）。
        見出し・案件名を「先頭1行だけ」とKeepTogetherし、案件ブロック全体を巻き込まない
        ようにするための分割。2つのテーブルの継ぎ目で罫線が二重にならないよう、
        先頭側は下端の罫線を、継続側は上端の罫線をそれぞれ消して1本の表に見せる。"""
        def _table(data_rows, suppress_bottom=False, suppress_top=False):
            data = [[P(_strip_bold(k), CELLB), P(_bold(v))] for k, v in data_rows]
            t = Table(data, colWidths=[label_w, W - label_w])
            style = _kv_style()
            if suppress_bottom:
                style.add("LINEBELOW", (0, -1), (-1, -1), 0, colors.white)
            if suppress_top:
                style.add("LINEABOVE", (0, 0), (-1, 0), 0, colors.white)
            t.setStyle(style)
            return t
        if not rows:
            return None, None
        first_tbl = _table(rows[:1], suppress_bottom=len(rows) > 1)
        rest_tbl = _table(rows[1:], suppress_top=True) if len(rows) > 1 else None
        return first_tbl, rest_tbl

    def prj(title, rows):
        """孤立防止（2026-08-05改修）: 案件ブロック全体ではなく「見出し＋テーブル最初の
        1行」だけをKeepTogetherする。案件全体を巻き込むと、大きな案件ブロックがページに
        収まらない場合に不自然に大きな空白を生む副作用があったため（本人指摘により発見）。
        呼び出し側は `st += prj(...)` を使うこと（リストを返すため）。"""
        first_tbl, rest_tbl = kv_split(rows)
        head = [Spacer(1, 1.8 * mm), Paragraph(title, H4)]
        if first_tbl:
            head += [Spacer(1, 0.8 * mm), first_tbl]
        out = [KeepTogether(head)]
        if rest_tbl:
            out.append(rest_tbl)
        return out

    st += [Paragraph("職 務 経 歴 書", TITLE), Spacer(1, 1.5 * mm),
           Paragraph(f"{data['date']}<br/>氏名: {_bold(data['name'])}", META)]

    def band_with_paras(heading, paras, style=BODY, gap=1.1 * mm):
        """見出し＋段落群。孤立防止のため最初の段落だけ見出しとKeepTogetherし、
        残りは従来通り個別に追加する（段落全体を巻き込んで大きな空白が出るのを防ぐ）。"""
        first = Paragraph(_bold(paras[0]), style) if paras else None
        out = band(heading, keep_with=first)
        for para in paras[1:]:
            out.append(Spacer(1, gap))
            out.append(Paragraph(_bold(para), style))
        return out

    # 職務要約
    st += band_with_paras("職務要約", data["summary"])

    # 活かせる経験（孤立防止: 最初の1項目だけ見出しとKeepTogether）
    skill_items = data["skill_items"]
    first_skill = None
    if skill_items:
        h0, b0 = skill_items[0]
        first_skill = [Spacer(1, 1.8 * mm), Paragraph(_bold(h0), H4), Spacer(1, 0.8 * mm),
                       Paragraph(_bold(b0), BODY)]
    st += band("活かせる経験・知識・スキル", keep_with=first_skill)
    for h, b in skill_items[1:]:
        st.append(KeepTogether([Spacer(1, 1.8 * mm), Paragraph(_bold(h), H4), Spacer(1, 0.8 * mm),
                                Paragraph(_bold(b), BODY)]))

    # マネジメント経験・語学（2026-08-05: 本人指示により職務経歴より前に移動。
    # 語学は独立バンドにせず、既存通りマネジメント経験と1つのバンドにまとめる
    # ——3行程度の短い語学情報のために見出しを1つ増やすと分量面で不利なため）
    # 孤立防止: 最初の1行だけ見出しとKeepTogether
    mgmt_lang = data["mgmt"] + data["lang"]
    li_style = S("li", 9.3, leading=13.5)
    first_li = Paragraph("・" + _bold(mgmt_lang[0]), li_style) if mgmt_lang else None
    st += band("マネジメント経験・語学", keep_with=first_li)
    for b in mgmt_lang[1:]:
        st.append(Paragraph("・" + _bold(b), li_style))

    # 自己PR（2026-08-05: 本人指示により職務経歴より前に移動。孤立防止: 最初の段落だけ
    # 見出しとKeepTogether——本人指摘により発見された「見出しがページ最下部に単独で
    # 残り本文が次ページに送られる」不具合の修正）
    pr_body = [p for p in data["pr"] if p != "以上"]
    st += band_with_paras("自己PR", pr_body)

    # 職務経歴（孤立防止: 会社名の見出し行だけ見出しとKeepTogether。表全体を巻き込むと
    # 大きな空白の副作用が出るリスクがあるため、表本体はKeepTogetherの対象外とする）
    def vendor_table(vendor_rows):
        # repeatRows=1: 表が途中で改ページされた場合もヘッダ行（ベンダー／製品／領域）を
        # 次ページ先頭に繰り返す（2026-08-05追加。ヘッダの無い続きが表示される事故を防ぐ）
        vt = Table([[P(x, CELLB) if i == 0 else P(_bold(x), CELL) for x in row]
                    for i, row in enumerate(vendor_rows)],
                   colWidths=[45 * mm, W - 45 * mm - 42 * mm, 42 * mm], repeatRows=1)
        vt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, SOFT),
                                ("BACKGROUND", (0, 0), (-1, 0), HEAD2),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                                ("TOPPADDING", (0, 0), (-1, -1), 1.0 * mm),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0 * mm)]))
        return vt

    companies = data["companies"]
    st += band("職務経歴", keep_with=Paragraph(companies[0]["name"], H3))
    for index, company in enumerate(companies):
        if index:
            st += [Spacer(1, 3.5 * mm), Paragraph(company["name"], H3)]
        st.append(Spacer(1, 1.1 * mm))
        if company["bullets"]:
            st.append(kv(company["bullets"]))
        if company["note"]:
            st += [Spacer(1, 0.8 * mm), Paragraph(f"※ {_bold(company['note'])}", SMALL)]
        for case in company["cases"]:
            if case["vendor"]:
                first_tbl, rest_tbl = kv_split(case["rows"])
                head = [Spacer(1, 2.2 * mm), Paragraph(case["name"], H4)]
                if first_tbl:
                    head += [Spacer(1, 0.9 * mm), first_tbl]
                st.append(KeepTogether(head))
                if rest_tbl:
                    st.append(rest_tbl)
                st += [Spacer(1, 1.1 * mm), vendor_table(case["vendor"])]
            else:
                st += prj(case["name"], case["rows"])

    # スキル（孤立防止: テーブル前に小さな緩衝要素が無いため、表全体を見出しとKeepTogether
    # する。表は9〜10行程度の中規模で1ページに収まる想定のため、大きな空白の副作用は限定的
    # ——生成後に必ず目視で確認すること）
    sk = [["分類", "内容", "レベル"]] + data["tech_rows"]
    skt = Table([[P(x, CELLB) if i == 0 else P(_bold(x), CELL) for x in r]
                for i, r in enumerate(sk)],
                colWidths=[42 * mm, W - 42 * mm - 44 * mm, 44 * mm], repeatRows=1)
    skt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, SOFT),
                             ("BACKGROUND", (0, 0), (-1, 0), HEAD2),
                             ("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                             ("TOPPADDING", (0, 0), (-1, -1), 1.0 * mm),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0 * mm)]))
    st += band("テクニカルスキル", keep_with=skt)

    # 資格（テクニカルスキルの直後、文書の最後に置く——保有資格の詳細一覧は参照情報のため）
    # 孤立防止: 見出し直後の「主要認定」小見出し（1行）だけをKeepTogetherし、
    # その下の表本体は対象外とする（表を巻き込むと大きな空白の副作用が出るリスクのため）
    cert = []
    cert += band("保有資格", keep_with=Paragraph("主要認定", H4))
    main = [["取得年月", "名称"]] + data["cert_main_rows"]
    mt = Table([[P(x, CELLB) if i == 0 else P(_bold(x), CELL) for x in r]
               for i, r in enumerate(main)],
               colWidths=[28 * mm, W - 28 * mm], repeatRows=1)
    mt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, SOFT),
                            ("BACKGROUND", (0, 0), (-1, 0), HEAD2),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                            ("TOPPADDING", (0, 0), (-1, -1), 1.0 * mm),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0 * mm)]))
    cert += [Spacer(1, 0.9 * mm), mt, Spacer(1, 2.2 * mm),
             Paragraph(data["cert_vendor_heading"], H4), Spacer(1, 0.9 * mm)]

    TAG = S("tag", 8.6, leading=12.3)
    # ⚠️ 2026-08-09: 従来は sn_groups（ExampleCloud）＋ (ms_heading, ms_body)（Microsoft）という
    # ベンダー名前提の合成をここで行っていた。load_shokumu() 側でベンダー非依存の
    # (ラベル, 本文) リストに畳んであるため、描画側はベンダーの件数も名前も知らなくてよい。
    groups = data["cert_vendor_items"]
    for h, b in groups:
        cert.append(KeepTogether([Paragraph(f"<b>{h}</b>", TAG), Paragraph(_bold(b), TAG),
                                  Spacer(1, 1.6 * mm)]))

    # 対応中の上位資格（結果待ち・受験予定）（CRMA・CTA等）。主要認定・ベンダー別認定とは別区分として明示的に描画
    # ——「取得済み」の一覧に混ぜないこと（2026-08-05・本人指示）
    if data.get("learning_heading"):
        cert += [Spacer(1, 1.0 * mm), Paragraph(data["learning_heading"], H4), Spacer(1, 0.9 * mm),
                 Paragraph(_bold(data["learning_body"]), TAG)]

    st += cert
    st += [Spacer(1, 2.2 * mm), Paragraph("以上", S("end", 9.5, alignment=TA_RIGHT))]

    doc.build(st)
    return path


# ================================================================== 英文レジュメ
# 本文がほぼ英字のため、CJK フォントのサブセット化パイプライン（JP/JPB）は使わず、
# reportlab 標準の Helvetica を使う（¥ ・ – — ® 等の記号が標準フォントで正しく出ることは
# PyMuPDF による抽出テストで確認済み）。したがって build_fonts() の成否に依存しない。
def build_resume_en(path, suffix):
    from reportlab.platypus import HRFlowable

    data = load_resume_en(suffix)
    doc, W = doc_template(path, top=15 * mm, bottom=15 * mm, left=17 * mm, right=17 * mm,
                          title=f"Resume - {data['name']}", footer_font="Helvetica", author=data["name"])
    st = []

    NAME = S("en_name", 20, font="Helvetica-Bold", leading=23, wordWrap=None)
    CONTACT = S("en_contact", 9.3, font="Helvetica", leading=13,
               textColor=colors.HexColor("#444444"), wordWrap=None)
    SEC = S("en_sec", 10.6, font="Helvetica-Bold", leading=13, textColor=ACC, wordWrap=None)
    BODY_EN = S("en_body", 9.4, font="Helvetica", leading=13.2, wordWrap=None)
    COMPANY = S("en_company", 10.2, font="Helvetica-Bold", leading=13, wordWrap=None)
    ROLE = S("en_role", 9.4, font="Helvetica", leading=12.8, wordWrap=None)
    CONTEXT = S("en_context", 9, font="Helvetica-Oblique", leading=12.5,
               textColor=colors.HexColor("#444444"), wordWrap=None)
    BULLET = S("en_bullet", 9.2, font="Helvetica", leading=12.6, leftIndent=10,
              firstLineIndent=-10, spaceAfter=2.4, wordWrap=None)
    CERTLINE = S("en_cert", 9.2, font="Helvetica", leading=12.8, spaceAfter=3, wordWrap=None)
    EDULINE = S("en_edu", 9.4, font="Helvetica", leading=13.2, spaceAfter=1.3, wordWrap=None)

    def section(title):
        return [Spacer(1, 3.6 * mm), Paragraph(title.upper(), SEC),
               HRFlowable(width="100%", thickness=0.7, color=ACC, spaceBefore=1, spaceAfter=2.6)]

    # --- ヘッダー（氏名・連絡先。写真・年齢・住所・性別は書かない）
    st += [Paragraph(_esc(data["name"]), NAME), Spacer(1, 0.8 * mm),
           Paragraph(_esc(data["contact"]), CONTACT),
           Spacer(1, 1.8 * mm), HRFlowable(width="100%", thickness=1.1, color=INK)]

    # --- Professional Summary
    st += section("Professional Summary")
    st.append(Paragraph(_bold(data["summary"]), BODY_EN))

    # --- Core Competencies
    st += section("Core Competencies")
    st.append(Paragraph(_bold(data["competencies"]), BODY_EN))
    st.append(Spacer(1, 1.3 * mm))
    st.append(Paragraph(_bold(data["languages"]), BODY_EN))

    # --- Professional Experience
    st += section("Professional Experience")
    for i, c in enumerate(data["companies"]):
        head_block = [Paragraph(_esc(c["name"]), COMPANY), Spacer(1, 0.7 * mm),
                      Paragraph(_bold(c["role"]), ROLE)]
        if c["context"]:
            head_block += [Spacer(1, 0.7 * mm), Paragraph(_bold(c["context"]), CONTEXT)]
        st.append(KeepTogether(head_block))
        if c["bullets"]:
            st.append(Spacer(1, 1.2 * mm))
            for b in c["bullets"]:
                st.append(Paragraph("•&nbsp;&nbsp;" + _bold(b), BULLET))
        if i < len(data["companies"]) - 1:
            st.append(Spacer(1, 3.2 * mm))

    # --- Certifications
    st += section("Certifications")
    for line in data["certs"]:
        st.append(Paragraph(_bold(line), CERTLINE))

    # --- Education
    st += section("Education")
    for line in data["education"]:
        st.append(Paragraph(_bold(line), EDULINE))

    doc.build(st)
    return path


if __name__ == "__main__":
    suffixes = _discover_suffixes()
    if not suffixes:
        raise RuntimeError(
            "documents/output/{接尾辞}/md/ に 履歴書_*_ja.md 等が見つかりません。"
            "先に documents/PROMPT.md に従って md を生成してください。")

    # ⚠️ 2026-08-10追加: 接尾辞を引数で指定できるようにした。
    # 従来は引数なしで実行すると**全応募先のPDFを再生成**する挙動しか無く、
    # 1社だけ生成したつもりで他社の提出済みPDFまで上書きする事故が実際に起きた
    # （archive/session_logs/SESSION_LOG_2026-08-09.md【23】）。応募先が複数ある状態では必ず接尾辞を指定すること。
    requested = sys.argv[1:]
    if requested:
        unknown = [r for r in requested if r not in suffixes]
        if unknown:
            raise SystemExit(
                f"未知の接尾辞: {unknown}\n  検出済みの接尾辞: {suffixes}")
        suffixes = requested
    elif len(suffixes) > 1:
        print(f"⚠️ 接尾辞が未指定のため、検出した全応募先を再生成します: {suffixes}")
        print("   1社だけ生成したい場合は接尾辞を引数に渡してください "
              "（例: python3 scripts/build_pdf.py ExampleCo_ExampleRole）")

    built = []
    for suffix in suffixes:
        print(f"=== {suffix} ===")
        os.makedirs(_out_dir(suffix, "md"), exist_ok=True)
        os.makedirs(_out_dir(suffix, "pdf"), exist_ok=True)
        pdf_dir = _out_dir(suffix, "pdf")
        paths = _md_paths(suffix)
        if os.path.exists(paths["rirekisho"]):
            built.append(build_rirekisho(os.path.join(pdf_dir, f"履歴書_{suffix}_ja.pdf"), suffix))
        if os.path.exists(paths["shokumu"]):
            built.append(build_shokumu(os.path.join(pdf_dir, f"職務経歴書_{suffix}_ja.pdf"), suffix))
        if os.path.exists(paths["resume_en"]):
            built.append(build_resume_en(os.path.join(pdf_dir, f"Resume_{suffix}_en.pdf"), suffix))
        if os.path.exists(paths["rirekisho_en"]):
            built.append(build_rirekisho_en(os.path.join(pdf_dir, f"履歴書_{suffix}_en.pdf"), suffix))

    for p in built:
        print("OK", os.path.relpath(p, BASE), os.path.getsize(p), "bytes")
