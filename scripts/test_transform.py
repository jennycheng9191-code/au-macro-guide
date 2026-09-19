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


def case_impersonate_profile_pinned():
    """common.IMPERSONATE 必須是釘版本的設定檔，不可以退回 "chrome"。

    "chrome" 是 curl_cffi 的浮動別名，指向套件當下的最新設定檔。
    2026-09-06 實測 melbourneinstitute.unimelb.edu.au：同一秒同一個網址，
    "chrome" 5 次有 4 次被 Cloudflare 回 403，"chrome124"／"chrome131" 全數 200。
    套件升級也可能讓 AOFM／finance.gov.au 無預警開始被擋，所以要釘死版本號。
    """
    import re as _re
    import common
    prof = getattr(common, "IMPERSONATE", "")
    return bool(_re.fullmatch(r"[a-z_]+\d[\w.]*", prof)),         f"IMPERSONATE = {prof!r}，必須帶版本號（如 chrome131）"


def case_mi_uses_impersonation():
    """melbourne_institute.py 必須走 get_impersonated。

    跟 ANZ 那條相反：MI 是 Cloudflare，一般 requests 幾乎必然 403。
    有人為了少一個相依把它改成 get_text，這張卡就會靜靜地變灰燈。
    """
    src = (Path(__file__).resolve().parent / "sources"
           / "melbourne_institute.py").read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]           # 跳過模組 docstring
    return "get_impersonated(" in body, "melbourne_institute.py 沒有呼叫 get_impersonated("


def case_mi_headline_sentence_forms():
    """MI 頭條句的四種語序都要解得出數值與月份。

    2026-09 那期把句型從「rose by 0.2 percentage points in August to 4.9 per cent」
    換成「was unchanged in September at 4.9 per cent」——月份在前、介系詞是 at，
    當時的正則三支全部不中，卡片停在 8 月。**這裡的字串是官方原文，不要改寫**：
    每期換句型是常態，靠這條在解析層先爆，而不是等排程亮黃燈才發現。
    """
    import sources.melbourne_institute as mi
    samples = [
        # 2026-09 實際原文（持平／月份在前／at）
        ("The expected inflation rate (30-per-cent trimmed mean measure) was unchanged "
         "in September at 4.9 per cent.", 4.9, "september"),
        # 2026-08 實際原文（上升／月份在前／to）
        ("The expected inflation rate (30-per-cent trimmed mean measure) rose by 0.2 "
         "percentage points in August to 4.9 per cent.", 4.9, "august"),
        # 另外兩種語序（數值在前）
        ("The expected inflation rate fell to 4.7 per cent in July.", 4.7, "july"),
        ("The expected inflation rate remained at 4.7 per cent in June.", 4.7, "june"),
    ]
    for text, want_v, want_m in samples:
        mm = mi._VALUE_RE.search(text)
        if not mm:
            return False, f"解不出數值：{text[:80]}"
        month, value = (mm.group(1), mm.group(2)) if mm.group(1) else \
                       (mm.group(4), mm.group(3)) if mm.group(3) else \
                       (mm.group(6), mm.group(5))
        if abs(float(value) - want_v) > 1e-9 or (month or "").lower() != want_m:
            return False, f"解出 {value}／{month}，應為 {want_v}／{want_m}：{text[:60]}"
    return True, ""


def case_westpac_description_forms():
    """Westpac description 的兩個坑：小數點與硬換行。

    兩者都在 2026-09 同時發作，而且都不會報錯，只會讓卡片沿用前值：
    - 變動幅度帶小數（`declined 5.2% to 84.4`）時，`[^.]*?` 會被那個點截斷；
      前一期是 `rose 6% to 88.9`（整數）才僥倖通過
    - description 裡留著字面上的 `\\r\\n`，把 `Leading Index` 切成兩段，
      desc_must 比對不到
    字串同樣是官方原文，照抄不要整形。
    """
    import sources.westpac_iq as w
    cases = [
        ("consumer_sentiment",
         "The Westpac–Melbourne Institute Consumer Sentiment Index declined 5.2% "
         "to 84.4 in September from 88.9 in August.", 84.4, "September"),
        ("leading_index",
         "The six-month annualised growth rate in the Westpac–Melbourne Institute "
         "Leading \\r\\nIndex, which indicates the likely pace of economic activity "
         "relative to trend three to \\r\\nnine months into the future, lifted to "
         "–0.09% in August from –0.17% in July.", -0.09, "August"),
    ]
    for series, raw, want_v, want_m in cases:
        spec = w.SPECS[series]
        desc = w._norm(raw)
        if not __import__("re").search(spec["desc_must"], desc, 2):
            return False, f"{series}：desc_must 比對不到（硬換行沒被攤平？）"
        mm = __import__("re").search(spec["pattern"], desc, 2)
        if not mm:
            return False, f"{series}：pattern 解不出數值：{desc[:90]}"
        if abs(w._num(mm.group(1)) - want_v) > 1e-9 or mm.group(2) != want_m:
            return False, f"{series}：解出 {mm.group(1)}／{mm.group(2)}，應為 {want_v}／{want_m}"
    return True, ""


def case_ft_pt_extras_keep_history():
    """就業人數增減的全職／兼職子項必須留著歷史，卡片才畫得出對照圖。

    `extras` 預設只留當期值（省 latest.json 體積），要畫圖得在 mapping 標
    `history: true`。這個旗標被拿掉時前端只會安靜地不畫圖——沒有錯誤、
    沒有黃燈，卡片看起來一切正常，所以釘在這裡。
    """
    import json
    m = json.loads((Path(__file__).resolve().parent.parent / "data" / "mapping.json")
                   .read_text(encoding="utf-8"))
    ex = (m.get("employment_change_ft_pt") or {}).get("extras") or {}
    missing = [k for k, v in ex.items() if not v.get("history")]
    return (len(ex) == 2 and not missing,
            f"這些子項沒有 history: true → {missing or '找不到全職／兼職兩個子項'}")


CASES = [
    ("缺漏月份時基期靠日期對齊", case_missing_month),
    ("基期不存在時跳過該點",     case_no_phantom_base),
    ("月變動計算",               case_mom),
    ("日頻序列的年比",           case_daily_yoy),
    ("ANZ mapping 的 series 有效", case_anz_mapping_series_valid),
    ("ANZ 用一般 requests 不偽裝", case_anz_uses_plain_requests),
    ("偽裝設定檔有釘版本",       case_impersonate_profile_pinned),
    ("MI 走偽裝指紋",            case_mi_uses_impersonation),
    ("MI 頭條句四種語序",        case_mi_headline_sentence_forms),
    ("Westpac description 兩個坑", case_westpac_description_forms),
    ("全職／兼職子項留歷史",     case_ft_pt_extras_keep_history),
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
