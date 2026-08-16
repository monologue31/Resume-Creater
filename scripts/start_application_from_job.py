#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""検索済みJDのスナップショットから、新しい応募先の正本を開始する。"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = BASE / "job_search" / "snapshots"
COMPANIES_DIR = BASE / "input" / "companies"


def main() -> int:
    parser = argparse.ArgumentParser(description="検索済みJDから応募先フォルダを開始")
    parser.add_argument("job_id", help="job_search/snapshots/linkedin_<ID>.md の求人ID")
    parser.add_argument("suffix", help="英数字と _ の応募先接尾辞（例: ExampleCo_ExampleRole）")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.suffix):
        raise SystemExit("suffix は英数字と _ のみ使用できます")
    snapshot = SNAPSHOT_DIR / f"linkedin_{args.job_id}.md"
    if not snapshot.exists():
        raise SystemExit(f"JDスナップショットがありません: {snapshot}\n先に scrape_jobs.py --save-detail {args.job_id} を実行してください")
    destination = COMPANIES_DIR / args.suffix
    if destination.exists():
        raise SystemExit(f"応募先フォルダが既に存在します: {destination}（上書きしません）")
    sources = destination / "sources"
    sources.mkdir(parents=True)
    target_snapshot = sources / "求人原文_提出時スナップショット.md"
    shutil.copy2(snapshot, target_snapshot)
    destination.joinpath("07_応募先.md").write_text(
        "# 応募先（求人原文から開始）\n\n"
        f"- **書類の接尾辞: `_{args.suffix}`**\n"
        f"- JD原文: [`sources/求人原文_提出時スナップショット.md`](sources/求人原文_提出時スナップショット.md)\n"
        "- 応募経路: ★\n"
        "- 応募着手日: ★\n\n"
        "> このファイルの会社名・職種・要件・ハードゲートは、上記スナップショットを唯一の出所として評価時に記入する。\n",
        encoding="utf-8",
    )
    print(f"作成: {destination.relative_to(BASE)}")
    print("次: 07_応募先.md に求人要約・ハードゲート・JD適合度を作成してから、書類定制に進んでください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
