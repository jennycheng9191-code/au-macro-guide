"""ISM 官方新聞稿抽取器的回歸測試。

分兩層：

  離線層  固定字串的單元測試，涵蓋踩過的坑（分項小標用 % 而非 percent、
          「3.1 percentage points」是變動量不是讀值）。改正則後必跑。

  連線層  自我一致性驗證：每篇新聞稿都會引述上個月的讀值，
          所以「我們從 M-1 月新聞稿解析出的值」必須出現在 M 月的新聞稿裡。
          分項數字沒有第三方可對照，這是唯一能自動抓到解析錯誤的辦法。
          加 --live 才會執行（會下載約 48 篇內文，約 1 分鐘）。

    .venv/Scripts/python.exe scripts/test_prnewswire.py [--live]
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "sources")]

import prnewswire as prn  # noqa: E402

# (內文片段, 分項標籤, 期望值, 說明)
CASES = [
    ("Business Activity Index at 55.4%; New Orders Index at 55.1%; "
     "Employment Index at 51.2%; Supplier Deliveries Index at 54.4%",
     "Employment Index", 51.2,
     "分項小標用 % 符號——只認 percent 會滑到下一句抓成別人的數字"),

    ("The Employment Index reading of 52.8 percent is up 3.1 percentage points "
     "from June's figure of 49.7 percent, putting the index in expansion territory.",
     "Employment Index", 52.8, "製造業就業：本期值在前、前值在後"),

    ("The Employment Index expanded for the first time in four months with a "
     "reading of 51.2 percent, a 3.3-percentage point increase from the 47.9 "
     "percent recorded in May.",
     "Employment Index", 51.2, "服務業就業：讀值與變動量混在同一句"),

    ("The New Orders Index expanded for the seventh consecutive month after four "
     "straight readings in contraction, registering 56.7 percent, up 0.7 "
     "percentage point compared to June's figure of 56 percent.",
     "New Orders Index", 56.7, "本期值前面隔著一長串沒有數字的敘述"),

    ("The Prices Index remained in expansion (or 'increasing' territory), "
     "registering 71.1 percent, a 1.9-percentage point decrease from June's "
     "reading of 73 percent.",
     "Prices Index", 71.1, "物價分項"),

    ("The Business Activity Index remained in expansion territory in June, "
     "decreasing 2.3 percentage points to 55.4 percent from May's reading of "
     "57.7 percent.",
     "Business Activity Index", 55.4, "變動量（2.3 percentage points）出現在讀值之前"),

    ("Gains in both the Business Activity and New Orders indexes were partially "
     "offset by the 3.3 percentage point increase in the Employment Index.",
     "Employment Index", None, "只有變動量、沒有讀值——必須回 None 而不是亂抓"),
]


def offline() -> list[str]:
    fails = []
    for text, label, want, why in CASES:
        got = prn._subindex(text, label)
        if got != want:
            fails.append(f"[{label}] {why}\n      期望 {want} / 實得 {got}")
    print(f"離線測試 通過 {len(CASES) - len(fails)}/{len(CASES)}")
    return fails


def _quoted(text: str, value: float) -> bool:
    """新聞稿引述前值時 56.0 會寫成「56 percent」，兩種寫法都算命中。"""
    return any(f"{v} " in text or f"{v}%" in text
               for v in ({f"{value:.1f}", f"{value:g}"}))


def live() -> list[str]:
    fails = []
    for card_id, (kind, label) in prn.CARDS.items():
        if label is None:
            continue                     # 總指數來自網址，不經內文解析
        res = prn.fetch(card_id, {})
        if not res["ok"]:
            fails.append(f"[{card_id}] 抓取失敗：{res['reason']}")
            continue

        hist = res["history"]
        by_date = {r["asof"]: r["url"] for r in prn._index()[kind]}
        checked = mismatch = revised = 0
        for prev, cur in zip(hist, hist[1:]):
            url = by_date.get(cur["date"])
            if not url:
                continue
            if _quoted(prn._body(url), prev["value"]):
                checked += 1
            elif cur["date"][5:7] == "01":
                # ISM 每年 1 月完成季調因子的年度修正，1 月號會引述修正後的
                # 12 月值（例：原始 47.7 → 修正 47.4）。對不上是正常的。
                revised += 1
            else:
                checked += 1
                mismatch += 1
                fails.append(f"[{card_id}] {prev['date'][:7]} 解析為 {prev['value']}，"
                             f"但 {cur['date'][:7]} 的新聞稿沒有引述這個數字")
        note = f"，年度季調修正邊界 {revised} 處（正常）" if revised else ""
        print(f"連線測試 {card_id:30s} 值={res['value']:<6} 歷史 {len(hist)} 期，"
              f"前後期互證 {checked - mismatch}/{checked}{note}")
    return fails


def main() -> int:
    fails = offline()
    if "--live" in sys.argv:
        print()
        fails += live()
    if fails:
        print("\n".join(["", "FAIL:"] + [f"  {f}" for f in fails]))
        return 1
    print("\n全部通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
