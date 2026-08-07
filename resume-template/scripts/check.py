#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整合性チェッカー

md（正本）と pdf（md から build_pdf.py が生成）の内容が一致しているか、
提出できる状態かを機械的に検証する。md が単一の情報源であり、pdf はそこから
機械生成されるため、以前のような「3か所を手作業で同期する」ズレは構造的に発生しない。
それでも pdf 生成が古いまま放置されていないかは確認する。

実行: python3 scripts/check.py
"""
import os, re, glob, subprocess, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_OUT = os.path.join(BASE, "documents", "output")
INPUT = os.path.join(BASE, "input")
# 2026-08-06: 面接準備の出力先として check_triplet(INT_OUT, ...) を過去に用意していたが、
# `interview/output/` は実在せず、実際の面接準備は rounds/*.md への直接編集で運用されていた
# （死コードだった。ARCHITECTURE.md／INTERVIEW_PROMPT.md参照）。検査対象から削除した。

# md/pdf で一致していなければならない重要な事実（日本語版・英語版どちらの語も混在可。
# 該当しない文書ではそもそも md 側にも出現しないため自動的にスキップされる）
# ⚠️ テンプレート化時の注記: 元プロジェクトではここに実際の案件の金額・人数・年月等の
# 具体的な文字列を列挙し、md→pdf変換で数値が欠落・改変されていないかを機械照合していた。
# テンプレートには個人情報を含めないため空にしてある。
# 使い方: 自分の職務経歴書・レジュメの中で「これだけは絶対に欠落してほしくない」という
# 固有名詞・数値（案件規模、資格名、年月等）を、md・pdf双方に実際に存在する表記のまま
# 文字列としてここに追加してください。多いほど検証は堅くなりますが、必須ではありません
# （空のままでも他のチェック——時系列順序・★残存確認・写真配置確認等——は機能します）。
KEY_FACTS = [
]
NG_WORDS = ["御社", "平成", "令和"]

# 提出用フォーマット（md/pdf）化を必要としない補助ドキュメントのファイル名プレフィックス
# （例: 推薦文＝Webフォームに貼る文章であり、独自のpdfを持たない）。
# REVIEW* は別枠（内部レビュー用メモ、そもそも生成物ではない）。
# 2026-08-06: 英文レジュメ_構成案・LinkedIn更新案・REVIEW* は提出完了後 documents/output/md/_archive/
# へ移動する運用にしたため、glob（非再帰）の対象から自然に外れる。このプレフィックス指定は
# 生成中（_archive移動前）の状態でも誤検知しないための保険として残す。
SUPPLEMENTARY_PREFIXES = ("推薦文", "英文レジュメ_構成案", "LinkedIn更新案")

ok, warn, err = [], [], []


def read_pdf(path):
    """pdftotext（poppler）があればそれを使い、無ければ PyMuPDF にフォールバックする。
    どちらも失敗した場合のみ None を返す（この場合、呼び出し側は比較をスキップすべきで、
    「空文字列として扱って一致チェックを通す」のは誤検知の温床になるため避ける）。"""
    try:
        return subprocess.run(["pdftotext", path, "-"], capture_output=True,
                              text=True, timeout=60).stdout
    except Exception:
        pass
    try:
        import fitz
        with fitz.open(path) as d:
            return "".join(page.get_text() for page in d)
    except Exception as e:
        warn.append(f"PDF を読めませんでした（pdftotext・PyMuPDF どちらも不可）: "
                    f"{os.path.basename(path)} / {e}")
        return None


def norm(s):
    """PDF 抽出時に入る改行・空白を吸収して比較できるようにする"""
    return re.sub(r"[\s　]+", "", s or "")


def check_triplet(outdir, label):
    """md（正本）と pdf（生成物）の内容が一致しているかを検証する。
    html は廃止済み（md → pdf の直接生成のため、html という中間形式は不要になった）。"""
    mds = sorted(glob.glob(os.path.join(outdir, "md", "*.md")))
    mds = [m for m in mds if not os.path.basename(m).startswith("REVIEW")
           and not os.path.basename(m).startswith(SUPPLEMENTARY_PREFIXES)]
    if not mds:
        warn.append(f"{label}: 生成物がまだありません")
        return
    for md in mds:
        stem = os.path.splitext(os.path.basename(md))[0]
        pdf = os.path.join(outdir, "pdf", stem + ".pdf")
        if not os.path.exists(pdf):
            err.append(f"{label}/{stem}: pdf が未生成")
            continue

        md_mtime = os.path.getmtime(md)
        pdf_mtime = os.path.getmtime(pdf)
        if md_mtime > pdf_mtime:
            warn.append(f"{label}/{stem}: md が pdf より新しい。"
                       f"python3 scripts/build_pdf.py の再実行が必要")

        t_md = norm(open(md, encoding="utf-8").read())
        raw_pdf = read_pdf(pdf)

        if raw_pdf is not None:
            t_pdf = norm(raw_pdf)
            gaps = []
            for f in KEY_FACTS:
                nf = norm(f)
                present = [nf in t_md, nf in t_pdf]
                if any(present) and not all(present):
                    where = [n for n, p in zip(("md", "pdf"), present) if not p]
                    gaps.append(f"「{f}」が {'/'.join(where)} に無い")
            if gaps:
                err.append(f"{label}/{stem}: md と pdf の内容が不一致\n      - " + "\n      - ".join(gaps))
            else:
                ok.append(f"{label}/{stem}: md / pdf の主要な数値が一致")

            for w in NG_WORDS:
                for name, txt in (("md", t_md), ("pdf", t_pdf)):
                    if norm(w) in txt:
                        err.append(f"{label}/{stem}({name}): 禁止語「{w}」を検出")

        # 提出前に潰すべき ★
        stars = open(md, encoding="utf-8").read().count("★")
        if stars:
            warn.append(f"{label}/{stem}: 未記入の ★ が {stars} 箇所（提出前に必ず潰すこと）")


def check_chronology():
    """履歴書（日本語版・英語版とも）の学歴・職歴・資格が時系列で並んでいるか。

    ⚠️ 2026-08-07: 「免許・資格」欄の先頭行に限り、時系列チェックから除外できる特例を
    追加した。日本の履歴書には「普通自動車免許は取得年月に関わらず資格欄の先頭に書く」
    という慣例があり（本人・2026-08-07確定）、これは意図的な非時系列の並びであって
    バグではない。ただし「先頭行なら何でも許容する」と緩めると本当の時系列ミスを
    見逃す危険があるため、**先頭行の内容が運転免許であることを確認したときだけ**
    例外を適用する（内容を見ずに機械的に先頭行を除外しない）。"""
    LICENSE_FIRST_ROW_EXEMPT_KEYWORDS = ("運転免許", "Driver", "Driving")
    for md in glob.glob(os.path.join(DOC_OUT, "md", "履歴書*.md")):
        txt = open(md, encoding="utf-8").read()
        # 日本語版は「### 学歴」「### 職歴」「## 免許・資格」、英語版は対応する英語見出しを見る
        for sec in ("学歴", "職歴", "免許・資格", "Education", "Work History", "Licenses / Qualifications"):
            m = re.search(rf"^#{{2,3}} {re.escape(sec)}\s*$(.*?)(?=^#{{1,3}} |\Z)", txt, re.S | re.M)
            if not m:
                continue
            rows = re.findall(r"^\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(.+?)\s*\|", m.group(1), re.M)
            ym = [(int(y), int(mo)) for y, mo, _desc in rows]
            check_ym = ym
            exempted = False
            if sec in ("免許・資格", "Licenses / Qualifications") and rows and \
               any(kw in rows[0][2] for kw in LICENSE_FIRST_ROW_EXEMPT_KEYWORDS):
                check_ym = ym[1:]
                exempted = True
            bad = [(check_ym[i], check_ym[i + 1]) for i in range(len(check_ym) - 1)
                  if check_ym[i] > check_ym[i + 1]]
            label = f"履歴書({os.path.basename(md)}) {sec}"
            if bad:
                err.append(f"{label}: 年月が逆転しています {bad}")
            elif ym:
                note = "（先頭行＝運転免許は慣例により時系列チェック対象外）" if exempted else ""
                ok.append(f"{label}: {len(ym)}行が時系列順{note}")


def check_input():
    stars = {}
    for p in sorted(glob.glob(os.path.join(INPUT, "**", "*.md"), recursive=True)):
        if os.path.basename(p) == "README.md":
            continue
        n = open(p, encoding="utf-8").read().count("★")
        if n:
            stars[os.path.relpath(p, BASE)] = n
    if stars:
        total = sum(stars.values())
        warn.append("input に未記入の ★ が計 %d 箇所:\n      " % total +
                    "\n      ".join(f"{k}: {v}" for k, v in sorted(stars.items(), key=lambda x: -x[1])))

    photo = glob.glob(os.path.join(INPUT, "assets", "photo.*"))
    (ok if photo else warn).append(
        "証明写真: 配置済み" if photo else "証明写真が未配置（JIS 履歴書が必要な場合のみ要対応）")


def check_status_sync():
    """選考ステータスの機械照合（2026-08-06導入）。
    interview/選考一覧.md（全社ダッシュボード）と、各社 interview/companies/{folder}/選考状況.md は
    同じ「現在地」を別ファイル・別粒度で持っており、従来は完全に手作業で同期していた。
    2026-08-06、実際に2箇所（選考一覧.md・README.md）でドリフト（提出済みなのに「提出待ち」の
    ままの記載）が発覚したため、機械照合できるようマーカーコメントを導入した。"""
    ichiran = os.path.join(BASE, "interview", "選考一覧.md")
    if not os.path.exists(ichiran):
        return
    txt = open(ichiran, encoding="utf-8").read()
    m = re.search(r"<!--STATUS-MAP\s*\n(.*?)-->", txt, re.S)
    if not m:
        warn.append("選考一覧.md: STATUS-MAPコメントが見つかりません（機械照合をスキップ）")
        return
    status_map = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        folder, status = line.split(":", 1)
        status_map[folder.strip()] = status.strip()

    for folder, expected in status_map.items():
        p = os.path.join(BASE, "interview", "companies", folder, "選考状況.md")
        if not os.path.exists(p):
            err.append(f"選考ステータス照合: {folder}/選考状況.md が見つかりません"
                      f"（選考一覧.mdのSTATUS-MAPに記載があるのに実体が無い）")
            continue
        sub = open(p, encoding="utf-8").read()
        sm = re.search(r"<!--\s*STATUS:\s*(.+?)\s*-->", sub)
        if not sm:
            warn.append(f"選考ステータス照合: {folder}/選考状況.md にSTATUSコメントがありません")
            continue
        actual = sm.group(1).strip()
        if actual != expected:
            err.append(f"選考ステータス照合: {folder} で不一致——"
                      f"選考一覧.md=「{expected}」 / 選考状況.md=「{actual}」"
                      f"\n      → どちらかが古い可能性。実態を確認し、両方を同じ文字列に揃えてください。")
        else:
            ok.append(f"選考ステータス照合: {folder} は選考一覧.md/選考状況.mdで一致（{actual}）")

    # 逆方向: companies/配下にあるのにSTATUS-MAPに載っていない応募先が無いか
    companies_dir = os.path.join(BASE, "interview", "companies")
    if os.path.isdir(companies_dir):
        for folder in sorted(os.listdir(companies_dir)):
            if folder not in status_map and os.path.exists(
                    os.path.join(companies_dir, folder, "選考状況.md")):
                warn.append(f"選考ステータス照合: {folder} が選考一覧.mdのSTATUS-MAPに未登録です")


def check_expiry():
    """有効期限が近い資格を拾う"""
    from datetime import date
    p = os.path.join(INPUT, "profile", "03_免許資格.md")
    if not os.path.exists(p):
        return
    txt = open(p, encoding="utf-8").read()
    today = date.today()
    for m in re.finditer(r"(20\d\d)-(\d\d)-(\d\d)", txt):
        d = date(*map(int, m.groups()))
        line = txt[max(0, m.start() - 120):m.start()].splitlines()[-1] if txt[:m.start()].splitlines() else ""
        if "期限" not in line and "有効" not in line:
            continue
        days = (d - today).days
        if days < 0:
            err.append(f"失効している資格があります（{d}）: {line.strip()[:60]}")
        elif days < 90:
            warn.append(f"あと{days}日で失効します（{d}）: {line.strip()[:60]}")


if __name__ == "__main__":
    check_triplet(DOC_OUT, "応募書類")
    check_chronology()
    check_input()
    check_expiry()
    check_status_sync()

    print("=" * 68)
    for label, items, mark in (("OK", ok, "  ✓ "), ("要確認", warn, "  ! "), ("エラー", err, "  ✗ ")):
        if items:
            print(f"\n[{label}] {len(items)}件")
            for i in items:
                print(mark + i)
    print("\n" + "=" * 68)
    print(f"OK {len(ok)} / 要確認 {len(warn)} / エラー {len(err)}")
    sys.exit(1 if err else 0)
