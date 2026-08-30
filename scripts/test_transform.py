"""序列轉換的回歸測試。

存在的理由：官方序列會有缺漏月份（FRED 的 CPIAUCNS 缺 2025-10，
政府停擺期間未採集 CPI）。第一版的 transform() 用「往回數 12 筆」找基期，
遇到缺漏就默默拿錯月份比較，把 CPI 年增率從 3.53% 算成 3.88%——
數字看起來完全合理，不對照官方來源根本不會發現。

    .venv/Scripts/python.exe scripts/test_transform.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import transform  # noqa: E402


def approx(a, b, tol=0.01):
    return a is not None and abs(a - b) < tol


def case_missing_month():
    """缺漏月份時，基期必須靠日期對齊，不能靠位置。"""
    # 用 BLS 官方實際數值：2025-06 = 322.561、2026-06 = 333.952 → YoY 3.53%
    # 序列刻意缺少 2025-10（與 FRED 實際情況相同）
    obs = [
        {"date": "2025-03-01", "value": 319.799},
        {"date": "2025-04-01", "value": 320.795},
        {"date": "2025-05-01", "value": 321.465},
        {"date": "2025-06-01", "value": 322.561},
        {"date": "2025-07-01", "value": 323.048},
        {"date": "2025-08-01", "value": 323.976},
        {"date": "2025-09-01", "value": 324.800},
        # 2025-10 缺漏
        {"date": "2025-11-01", "value": 324.122},
        {"date": "2025-12-01", "value": 324.054},
        {"date": "2026-01-01", "value": 325.252},
        {"date": "2026-02-01", "value": 326.785},
        {"date": "2026-03-01", "value": 330.213},
        {"date": "2026-04-01", "value": 333.020},
        {"date": "2026-05-01", "value": 335.123},
        {"date": "2026-06-01", "value": 333.952},
    ]
    out = transform(obs, "yoy", "M")
    latest = out[-1]
    ok = latest["date"] == "2026-06-01" and approx(latest["value"], 3.53, 0.02)
    return ok, f"2026-06 YoY 期望 3.53%，實得 {latest['value']:.2f}%（日期 {latest['date']}）"


def case_no_phantom_base():
    """基期不存在時應該跳過該點，不可拿鄰近月份硬湊。"""
    obs = [
        {"date": "2025-06-01", "value": 100.0},
        {"date": "2026-05-01", "value": 110.0},   # 基期 2025-05 不存在
        {"date": "2026-06-01", "value": 105.0},   # 基期 2025-06 存在
    ]
    out = transform(obs, "yoy", "M")
    ok = len(out) == 1 and out[0]["date"] == "2026-06-01" and approx(out[0]["value"], 5.0)
    return ok, f"應只產生 1 點（2026-06 = 5.00%），實得 {[(o['date'], round(o['value'],2)) for o in out]}"


def case_mom():
    obs = [
        {"date": "2026-04-01", "value": 100.0},
        {"date": "2026-05-01", "value": 102.0},
        {"date": "2026-06-01", "value": 101.0},
    ]
    out = transform(obs, "mom", "M")
    ok = approx(out[-1]["value"], -0.98, 0.01)
    return ok, f"MoM 期望 -0.98%，實得 {out[-1]['value']:.2f}%"


def case_daily_yoy():
    """日頻序列沒有整齊日期，應取目標日之前最近的一筆。"""
    obs = [
        {"date": "2025-06-27", "value": 2.00},
        {"date": "2025-06-30", "value": 2.10},
        {"date": "2026-06-29", "value": 2.30},
        {"date": "2026-06-30", "value": 2.40},
    ]
    out = transform(obs, "yoy", "D")
    ok = len(out) >= 1 and out[-1]["date"] == "2026-06-30"
    return ok, f"日頻應算得出 YoY，實得 {[(o['date'], round(o['value'],2)) for o in out]}"


def case_anz_mapping_series_valid():
    """mapping 的 anz series 必須是 anz.COLS 的鍵。

    打錯字不會讓建置失敗，只會讓那張卡默默變成未取得——
    fetch() 走的是「回 ok=False」而不是丟例外，防呆會照樣過。
    """
    import json
    sys.path.insert(0, str(Path(__file__).resolve().parent / "sources"))
    import anz

    mp = json.loads((Path(__file__).resolve().parent.parent
                     / "data" / "mapping.json").read_text(encoding="utf-8"))
    bad = [k for k, v in mp.items()
           if isinstance(v, dict) and v.get("source") == "anz"
           and v.get("series", "sa") not in anz.COLS]
    return not bad, f"series 不在 anz.COLS 的卡：{bad}（可用 {list(anz.COLS)}）"


def case_anz_uses_plain_requests():
    """anz.py 不可改用 get_impersonated。

    anz.com.au 的擋法跟 AOFM／finance.gov.au **相反**：一般 requests 回 200，
    curl_cffi 偽裝 Chrome 指紋反而 403。之後有人「統一改成偽裝指紋比較保險」
    會讓這張卡整個抓不到，而錯誤訊息只會說取得失敗，看不出是偽裝害的。
    """
    src = (Path(__file__).resolve().parent / "sources" / "anz.py").read_text(encoding="utf-8")
    kept = [l for l in src.splitlines() if not l.strip().startswith("#")]
    code = chr(10).join(kept)
    body = code.split('"""', 2)[-1]          # 跳過模組 docstring，註解裡有提到這個字
    return "get_impersonated(" not in body, "anz.py 出現了 get_impersonated( 呼叫"


CASES = [
    ("缺漏月份時基期靠日期對齊", case_missing_month),
    ("基期不存在時跳過該點",     case_no_phantom_base),
    ("月變動計算",               case_mom),
    ("日頻序列的年比",           case_daily_yoy),
    ("ANZ mapping 的 series 有效", case_anz_mapping_series_valid),
    ("ANZ 用一般 requests 不偽裝", case_anz_uses_plain_requests),
]


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            ok, detail = fn()
        except Exception as e:                       # noqa: BLE001
            ok, detail = False, f"例外：{e}"
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"      {detail}")
            failed += 1
    print(f"\n通過 {len(CASES) - failed}/{len(CASES)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
