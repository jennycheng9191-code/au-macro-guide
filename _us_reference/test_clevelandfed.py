"""Cleveland Fed 通膨即時預測抽取器的回歸測試。

鎖住開發時踩到的兩個坑，兩個都不會讓程式報錯、只會安靜給出錯的東西：

  1. categories 裡混了事件標記（"CPI Jun"），不濾掉會讓整條序列與日期錯位
  2. Actual 空缺不只出現在「還沒公布」的月份，歷史區間中間也有
     （2013-07 資料缺漏、2025-10 政府停擺期間未採集），從頭掃會選到十幾年前

    .venv/Scripts/python.exe scripts/test_clevelandfed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "sources")]

import clevelandfed as cf  # noqa: E402


def _el(subcaption: str, labels: list[str], actual: list[str] | None = None) -> dict:
    """組一個最小可用的圖表元素。

    真實檔案裡事件標記只出現在 categories、不占資料點，
    所以 nowcast 序列的長度＝日期標籤數（不含標記）。
    """
    dates = [x for x in labels if "/" in x]
    return {
        "chart": {"subcaption": subcaption},
        "categories": [{"category": [{"label": x} for x in labels]}],
        "dataset": [
            {"seriesname": "Core CPI Inflation",
             "data": [{"value": "0.2"} for _ in dates]},
            {"seriesname": "Actual Core CPI Inflation",
             "data": [{"value": v} for v in (actual or [])]},
        ],
    }


FAILS: list[str] = []


def check(name: str, got, want):
    if got != want:
        FAILS.append(f"{name}\n      期望 {want}\n      實得 {got}")


# ---- 1. 事件標記必須整個濾掉，不能留空位 ----
el = _el("2026-7", ["07/01", "07/02", "CPI Jun", "07/03", "PCE Jun", "08/04"])
check("事件標記濾除後只剩日期",
      cf._observation_dates(el, 2026, 7),
      ["2026-07-01", "2026-07-02", "2026-07-03", "2026-08-04"])

check("濾除後的日期數要等於資料筆數（否則 fetch 會放棄歷史）",
      len(cf._observation_dates(el, 2026, 7)),
      len(cf._series(el, "Core CPI Inflation")))

# ---- 2. 跨年：12 月的目標月，觀測日會延伸到隔年 1 月 ----
el = _el("2025-12", ["12/30", "12/31", "01/02"])
check("12 月目標月的隔年 1 月觀測日",
      cf._observation_dates(el, 2025, 12),
      ["2025-12-30", "2025-12-31", "2026-01-02"])

# ---- 3. 選月：只認檔尾連續未公布的那段 ----
arr = [
    _el("2013-7", ["07/01"], actual=[]),        # 歷史資料缺漏
    _el("2025-9", ["09/01"], actual=["0.3"]),
    _el("2025-10", ["10/01"], actual=[]),       # 政府停擺期間未採集
    _el("2025-11", ["11/01"], actual=["0.2"]),
    _el("2026-6", ["06/01"], actual=["0.1"]),   # 最近一個已公布
    _el("2026-7", ["07/01"], actual=[]),        # ← 應選這個
    _el("2026-8", ["08/01"], actual=[]),
]
target, prior = cf._pick_target(arr, "Actual Core CPI Inflation")
check("目標月＝檔尾連續未公布中最早的那個", cf._month_of(target), (2026, 7))
check("上期＝檔尾往回第一個已公布的", cf._month_of(prior), (2026, 6))

# ---- 4. 全部都已公布時不該挑出目標月 ----
target, prior = cf._pick_target(
    [_el("2026-5", ["05/01"], actual=["0.1"]), _el("2026-6", ["06/01"], actual=["0.2"])],
    "Actual Core CPI Inflation")
check("沒有未公布月份時 target 為 None", target, None)
check("此時 prior 仍取得最後一個月", cf._month_of(prior), (2026, 6))


def main() -> int:
    total = 7
    if FAILS:
        print(f"通過 {total - len(FAILS)}/{total}\n")
        print("\n".join(f"FAIL  {f}" for f in FAILS))
        return 1
    print(f"通過 {total}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
