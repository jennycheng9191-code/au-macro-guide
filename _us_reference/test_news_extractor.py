"""新聞抽取器的回歸測試。

這是整套系統風險最高的一段——ISM 六張卡與 ADP 都靠它。
每次調整 news.py 的正則後執行：
    .venv/Scripts/python.exe scripts/test_news_extractor.py

判準不是「盡量抓到」，而是「絕不抓錯」。抓不到會亮黃燈由人補，
抓錯了不會有人發現。所以所有陷阱句的期望值都是 None。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "sources")]

import news  # noqa: E402

# (卡片 id, 句子, 期望值, 說明)
CASES = [
    # ---- 正例：應該抓到 ----
    ("ism_manufacturing_pmi",
     "The ISM said its manufacturing PMI fell to 48.2 last month from 49.5 in June.",
     48.2, "標準寫法"),
    ("ism_manufacturing_pmi",
     "The manufacturing index came in at 48.2, down from 49.5 the prior month, "
     "the Institute for Supply Management said.",
     48.2, "指標在前、機構在後，且中間夾帶含小數點的前值"),
    ("ism_services_pmi",
     "The Institute for Supply Management's services PMI rose to 52.4 in July.",
     52.4, "服務業標準寫法"),
    ("ism_mfg_prices_paid",
     "The prices paid index registered 63.7, the highest since 2022.",
     63.7, "物價分項"),
    ("ism_mfg_new_orders",
     "The forward-looking new orders index slipped to 45.3 from 47.1.",
     45.3, "新訂單分項"),
    ("adp_national_employment_report",
     "ADP reported private sector payrolls increased by 104,000 in July.",
     104.0, "ADP 標準寫法——新聞寫人數，卡片單位是千人，抽取器要換算"),

    # ---- 陷阱：全部必須回 None ----
    ("ism_manufacturing_pmi",
     "Economists polled by Reuters expected the manufacturing PMI to be 49.0.",
     None, "預期值，不可誤抓"),
    ("ism_manufacturing_pmi",
     "Manufacturing PMI was 51.0 a year ago, compared with 48.2 now.",
     None, "歷史比較句，語境不明確時寧可不抓"),
    ("ism_manufacturing_pmi",
     "The consensus forecast for the manufacturing index was 49.5.",
     None, "共識預估值"),
    ("ism_services_pmi",
     "China's services PMI came in at 50.1, a private survey showed.",
     None, "他國 PMI，無 ISM 語境"),
    ("ism_manufacturing_pmi",
     "The manufacturing PMI is expected to hit 47.5 next month.",
     None, "未來預期"),
]


def main() -> int:
    passed, failed = 0, []
    for cid, text, want, why in CASES:
        got = news._extract(text, cid)
        if got == want:
            passed += 1
        else:
            failed.append((cid, text, want, got, why))

    for cid, text, want, got, why in failed:
        print(f"FAIL  [{cid}] {why}")
        print(f"      期望 {want} / 實得 {got}")
        print(f"      句子：{text}")

    print(f"\n通過 {passed}/{len(CASES)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
