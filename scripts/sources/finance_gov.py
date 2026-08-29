"""finance.gov.au 月度財政帳（Commonwealth Monthly Financial Statements）。

供兩張卡使用：月度財政帳（基本現金餘額）與淨/毛負債水位。

**為什麼負債水位走這裡而不是 AOFM**：AOFM data-hub 的 `stock_ags.csv` 是**年頻**，
2026-08-29 實測只到 FY2024-25（落後一整個財年）。月度財政帳每月更新，
而且同一頁就同時給毛債（Government securities）與淨債（Net debt），
還附官方預算估計值可對照。

**擋法**：finance.gov.au 與 aofm.gov.au 同屬 Akamai 靜默丟棄，必須走
`common.get_impersonated`（curl_cffi 模擬 Chrome TLS 指紋）。

**不必解 PDF**。每期都有 PDF 附件，但整份聲明的數字在 HTML 內文裡就有，
解 HTML 省掉一個 PDF 相依。錨點選得很保守：

- 基本現金餘額／財政餘額 → 錨在**逐期固定的敘述句**
  「The underlying cash balance for the YYYY-YY financial year to DD Month YYYY
    was a deficit/surplus of $X billion」
- 淨債／毛債 → 錨在**表格列名**（`Net debt`、`Government securities`），
  數字取列名後的第一個數（同列第二個數是預算估計值，另存成 extras）

**期別怎麼定**：用敘述句裡的「to 31 May 2026」，不是用發布日。
六月那一期不會發布——財年結束改由 9 月的 Final Budget Outcome 取代，
所以 stale_days 要留到能跨過這個空窗（見 mapping）。

赤字一律以**負值**表示（官方文字寫 "deficit of $10.9 billion"），
盈餘為正。這樣走勢圖的方向才跟直覺一致：往上＝財政改善。
"""
from __future__ import annotations

import html as _html
import re

from common import get_impersonated

INDEX = "https://www.finance.gov.au/publications/commonwealth-monthly-financial-statements"
BASE = "https://www.finance.gov.au"

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"], 1)}

_page_cache: dict[str, str] = {}


def _text(raw: str) -> str:
    """去標籤但**保留分隔**——表格數字若黏在一起會解成錯的數。

    必須先 `html.unescape()`：這一頁的敘述句裡到處是 `&nbsp;`
    （"to 31&nbsp;May&nbsp;2026"），只去標籤不解實體的話，
    留下來的是字面的 "&nbsp;" 字串，任何用 `\\s+` 的正則都對不上。
    連字號也統一：官方文字用的是 U+2011 不斷行連字號。
    """
    t = re.sub(r"<[^>]+>", " ", raw)
    t = _html.unescape(t)
    t = t.replace("\xa0", " ").replace("‑", "-").replace("–", "-")
    return re.sub(r"[ \t]+", " ", t)


def latest_page() -> tuple[str, str]:
    """回傳（最新一期的網址, 該期年月字串如 'may 2026'）。

    索引頁的連結標題是「Monthly Financial Statements for May 2026」，
    路徑是 `/2026/mfs-may`。**路徑裡的年份是財政年度不是日曆年**
    （2025 年 12 月那期在 `/2026/mfs-december`），所以期別一律從標題取，
    不從路徑推。
    """
    html = get_impersonated(INDEX)
    found: list[tuple[tuple[int, int], str, str]] = []
    for href, title in re.findall(r'href="([^"]+)"[^>]*>\s*([^<]{10,120}?)\s*</a>', html):
        t = " ".join(title.split())
        mm = re.search(r"Monthly Financial Statements for\s+([A-Za-z]+)\s+(\d{4})", t)
        if not mm or "/mfs-" not in href:
            continue
        mon = _MONTHS.get(mm.group(1).lower())
        if not mon:
            continue
        year = int(mm.group(2))
        found.append(((year, mon), href if href.startswith("http") else BASE + href,
                      f"{mm.group(1).lower()} {year}"))
    if not found:
        raise RuntimeError("finance.gov.au 索引頁找不到任何月度財政帳連結")
    found.sort()
    _, url, period = found[-1]
    return url, period


def _page(url: str) -> str:
    if url not in _page_cache:
        _page_cache[url] = get_impersonated(url)
    return _page_cache[url]


def _num(s: str) -> float | None:
    s = s.replace(",", "").strip()
    neg = s.startswith("-") or s.startswith("−")
    s = s.lstrip("-−")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _balance(text: str, kind: str) -> tuple[float | None, str]:
    """從敘述句取『基本現金餘額』或『財政餘額』，回傳（十億澳元, 期別 YYYY-MM-01）。

    赤字轉成負值。句型逐期固定，這是本模組最穩的錨點。
    """
    pat = (rf"The {kind} for the .*?financial year to\s+(\d{{1,2}})\s+([A-Za-z]+)\s+(\d{{4}})"
           rf"\s+was a\s+(deficit|surplus)\s+of\s+\$([\d,.]+)\s*billion")
    mm = re.search(pat, text, re.I)
    if not mm:
        return None, ""
    v = _num(mm.group(5))
    if v is None:
        return None, ""
    if mm.group(4).lower() == "deficit":
        v = -v
    mon = _MONTHS.get(mm.group(2).lower())
    asof = f"{int(mm.group(3)):04d}-{mon:02d}-01" if mon else ""
    return round(v, 2), asof


def agg_row(text: str, label: str) -> list[float]:
    """取 AGGREGATES 表某一列的四個數字。

    表頭固定是這四欄，順序不變（2026-08-29 實測 may 2026 那期）：

        [0] ACTUAL 當月
        [1] ACTUAL 本財年迄今（YTD）
        [2] Revised Budget Profile 同期預算進度
        [3] REVISED BUDGET ESTIMATE 全年估計   ← 年度預算卡要的就是這個

    例：`Underlying cash balance 12.0 -10.9 -18.5 -28.3`
    ——當月盈餘 12.0、迄今赤字 10.9、照預算進度本應赤字 18.5、全年估計赤字 28.3。

    錨在列名而不是列序：財政帳的科目逐年會增刪，照列序抓會在改版當期
    悄悄抓到隔壁科目。數字沿用官方符號，赤字本來就是負的，不必再轉。
    """
    mm = re.search(rf"\b{re.escape(label)}\s*(?:\([a-z]\))?\s*"
                   rf"((?:[-−]?[\d,]+\.?\d*\s+){{3,4}})", text, re.I)
    if not mm:
        return []
    return [n for n in (_num(x) for x in mm.group(1).split()) if n is not None]


def fy_label(text: str) -> str:
    """從表頭取財政年度字串，例如 '2025-26'。"""
    mm = re.search(r"REVISED BUDGET ESTIMATE\*?\s*(\d{4})-(\d{4})", text, re.I)
    if mm:
        return f"{mm.group(1)}-{mm.group(2)[2:]}"
    mm = re.search(r"AGGREGATES\(?a?\)?\s*ACTUAL\s*(\d{4})-(\d{4})", text, re.I)
    return f"{mm.group(1)}-{mm.group(2)[2:]}" if mm else ""


def _table_row(text: str, label: str) -> tuple[float | None, float | None]:
    """取表格某一列的前兩個數字（實際值, 預算估計值）。

    錨在列名而不是列序：財政帳的表格列數逐年會變（新增/合併科目），
    照列序抓會在改版當期悄悄抓到隔壁科目。
    """
    mm = re.search(rf"{re.escape(label)}\s*(?:\([a-z]\))?\s*((?:[-−]?[\d,]+\.?\d*\s+){{1,2}})",
                   text, re.I)
    if not mm:
        return None, None
    nums = [_num(x) for x in mm.group(1).split()]
    nums = [n for n in nums if n is not None]
    return (nums[0] if nums else None, nums[1] if len(nums) > 1 else None)


def fetch(card_id: str, m: dict) -> dict:
    want = m.get("field")
    try:
        url, period = latest_page()
        html = _page(url)
    except Exception as e:                              # noqa: BLE001
        return {"ok": False, "reason": f"finance.gov.au 取得失敗：{e}"}

    text = _text(html)

    # 期別一律取自敘述句的「to 31 May 2026」，不用發布日
    _, asof = _balance(text, "underlying cash balance")
    fy = fy_label(text)

    if want == "underlying_cash_balance":
        # 月度累計：主值取 AGGREGATES 表的 YTD 欄，與敘述句交叉核對
        row = agg_row(text, "Underlying cash balance")
        v, asof2 = _balance(text, "underlying cash balance")
        if v is None and len(row) < 2:
            return {"ok": False, "reason": f"{period} 那期找不到基本現金餘額"}
        if len(row) >= 2:
            # 表與敘述句差超過 0.1 十億就是有一邊解錯了，寧可不上架
            if v is not None and abs(row[1] - v) > 0.1:
                return {"ok": False,
                        "reason": f"敘述句({v})與 AGGREGATES 表({row[1]})對不上，不採用"}
            v = row[1]
        asof = asof2 or asof
        fis = agg_row(text, "Fiscal balance")
        extras = {
            "當月(十億)": row[0] if len(row) >= 1 else None,
            "預算進度應為(十億)": row[2] if len(row) >= 3 else None,
            "財政餘額迄今(十億)": fis[1] if len(fis) >= 2 else None,
        }

    elif want == "budget_full_year":
        # 年度預算卡：主值取全年估計欄，隨 Budget 與 MYEFO 改版而更新
        row = agg_row(text, "Underlying cash balance")
        if len(row) < 4:
            return {"ok": False,
                    "reason": f"{period} 那期的 AGGREGATES 表沒有全年估計欄（取到 {row}）"}
        v = row[3]
        fis = agg_row(text, "Fiscal balance")
        extras = {
            "本財年迄今實際(十億)": row[1],
            "財政餘額全年估計(十億)": fis[3] if len(fis) >= 4 else None,
            "財政年度": fy or None,
        }

    elif want == "net_debt":
        net, net_budget = _table_row(text, "Net debt")
        gross, _ = _table_row(text, "Government securities")
        if net is None:
            return {"ok": False, "reason": f"{period} 那期的表格找不到 Net debt 列"}
        v = round(net, 1)
        extras = {
            # Government securities 在表裡的單位是百萬澳元，換成十億才跟淨債同尺
            "毛債·政府證券(十億)": round(gross / 1000, 1) if gross else None,
            "預算估計淨債(十億)": round(net_budget, 1) if net_budget else None,
        }
    else:
        return {"ok": False, "reason": f"mapping 的 field 未知：{want}"}

    if not asof:
        return {"ok": False, "reason": f"{period} 那期解不出期別"}

    return {
        "ok": True,
        "value": v,
        "asof": asof,
        "history": [],          # 官方沒有免費歷史檔，靠 build.py 的 persist_history 累積
        "raw_latest": v,
        "freq": "M",
        "extras": extras,
        "also": {},
        "source_label": m.get("source_label") or f"財政部月度財政帳（{period}）",
    }
