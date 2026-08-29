"""Westpac IQ——消費者信心指數與領先指標。

**為什麼不去 Melbourne Institute 抓**：這兩個指標掛的是
「Westpac–Melbourne Institute」聯名，但 melbourneinstitute.unimelb.edu.au
**全站對程式化請求回 403**，連根目錄都擋，curl_cffi 模擬 Chrome 指紋也不通
（2026-08-15 首次確認，2026-08-29 重驗仍是 403）。
Westpac 自己的 IQ 站發同一份報告，且沒有反爬——繞這邊走。

同一批裡的**消費者通膨預期**（Melbourne Institute Inflation Expectations）
沒有這條路可繞：Westpac IQ 只在「下週看點」的行事曆提到它，不發數字。那張卡維持人工。

**解析錨點是 JSON-LD 的 description 欄**，不是內文敘述。
Westpac 每篇文章的結構化資料裡都有一句話把頭條數字講完：

    "The Westpac-Melbourne Institute Consumer Sentiment Index rose 6% to 88.9
     in August from 83.9 in July."

    "The six-month annualised growth rate in the Westpac-Melbourne Institute
     Leading Index ... lifted to -0.2% in July from -0.4% in June."

錨在這裡比錨在內文安全得多：內文的敘述句每期改寫，description 是固定樣板。

**期別要從句子裡的月份取，不是從文章日期取。** 領先指標尤其明顯——
8 月發布的那篇報的是**7 月**的數據。照文章月份標期別會整整早一個月。

單位：消費者信心是指數（100 = 樂觀與悲觀人數相等），領先指標是
六個月年化成長率（%，相對趨勢）。兩者都可能是負號，而 Westpac 用的是
Unicode 連接號 U+2013 而不是 ASCII 減號，正則要一起吃。
"""
from __future__ import annotations

import datetime as dt
import html as _html
import re

from common import get_impersonated

HOME = "https://www.westpaciq.com.au"

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"], 1)}

_page_cache: dict[str, str] = {}

# 兩張卡的解析規格。pattern 的第一個群組是數值、第二個是月份。
SPECS = {
    "consumer_sentiment": {
        "slug": "consumer-sentiment",
        "desc_must": r"Consumer Sentiment Index",
        "pattern": r"Consumer Sentiment Index[^.]*?\bto\s+([-−–]?[\d.]+)\s+in\s+([A-Za-z]+)",
        "prior": r"from\s+([-−–]?[\d.]+)\s+in\s+([A-Za-z]+)",
        "label": "Westpac–MI 消費者信心指數",
    },
    "leading_index": {
        "slug": "leading-index",
        "desc_must": r"Leading Index",
        "pattern": r"Leading Index[^.]*?\bto\s+([-−–]?[\d.]+)%\s+in\s+([A-Za-z]+)",
        "prior": r"from\s+([-−–]?[\d.]+)%\s+in\s+([A-Za-z]+)",
        "label": "Westpac–MI 領先指標（六個月年化）",
    },
}


def _num(s: str) -> float | None:
    """吃 ASCII 減號與 Unicode 連接號（Westpac 用 U+2013）。"""
    s = s.strip().replace("−", "-").replace("–", "-")
    try:
        return float(s)
    except ValueError:
        return None


def _home() -> str:
    if HOME not in _page_cache:
        _page_cache[HOME] = get_impersonated(HOME)
    return _page_cache[HOME]


def latest_path(slug: str) -> str:
    """從首頁撈出該 slug 最新一期的文章路徑。

    路徑格式 `/economics/YYYY/MM/{slug}-{monthname}-YYYY`，
    照年月排序取最後一筆——不靠首頁的版面順序，版面會依編輯權重調動。
    """
    home = _home()
    found: list[tuple[tuple[int, int], str]] = []
    for p in set(re.findall(rf'"(/economics/(\d{{4}})/(\d{{2}})/{slug}-[a-z]+-\d{{4}})"', home)):
        path, y, mo = p
        found.append(((int(y), int(mo)), path))
    if not found:
        raise RuntimeError(f"Westpac IQ 首頁找不到 {slug} 的文章連結")
    found.sort()
    return found[-1][1]


def _description(url: str, must: str) -> str:
    if url not in _page_cache:
        _page_cache[url] = get_impersonated(url)
    raw = _page_cache[url]
    cands = [_html.unescape(m.group(1))
             for m in re.finditer(r'"description":"([^"]{25,600})"', raw)]
    for d in cands:
        if re.search(must, d, re.I):
            return d.replace("\\u2013", "–").replace("\\/", "/")
    raise RuntimeError(f"文章裡找不到含「{must}」的 description 欄（共 {len(cands)} 段）")


def _asof(month_name: str, published: tuple[int, int]) -> str:
    """把句子裡的月份配上正確的年份。

    只有月名沒有年份，所以用文章的年月回推：資料月份必定在發布月份
    當月或之前，若月號比發布月大就是去年（12 月的資料在 1 月發布）。
    """
    mon = _MONTHS.get(month_name.lower())
    if not mon:
        raise RuntimeError(f"看不懂的月份：{month_name}")
    year, pub_mon = published
    if mon > pub_mon:
        year -= 1
    return f"{year:04d}-{mon:02d}-01"


def fetch(card_id: str, m: dict) -> dict:
    spec = SPECS.get(m.get("series"))
    if not spec:
        return {"ok": False, "reason": f"mapping 的 series 未知：{m.get('series')}"}

    try:
        path = latest_path(spec["slug"])
        pub = (int(path.split("/")[2]), int(path.split("/")[3]))
        desc = _description(HOME + path, spec["desc_must"])
    except Exception as e:                              # noqa: BLE001
        return {"ok": False, "reason": f"Westpac IQ 取得失敗：{e}"}

    mm = re.search(spec["pattern"], desc, re.I)
    if not mm:
        return {"ok": False, "reason": f"description 解不出數值：{desc[:120]}"}
    value = _num(mm.group(1))
    if value is None:
        return {"ok": False, "reason": f"數值轉換失敗：{mm.group(1)!r}"}

    try:
        asof = _asof(mm.group(2), pub)
    except Exception as e:                              # noqa: BLE001
        return {"ok": False, "reason": str(e)}

    extras = {}
    if (pm := re.search(spec["prior"], desc[mm.end():], re.I)):
        prior = _num(pm.group(1))
        if prior is not None:
            extras["前期值"] = prior
            extras["較前期"] = round(value - prior, 2)

    return {
        "ok": True,
        "value": value,
        "asof": asof,
        "history": [],      # Westpac 不提供免費歷史序列，靠 persist_history 累積
        "raw_latest": value,
        "freq": "M",
        "extras": extras,
        "also": {},
        "source_label": m.get("source_label") or spec["label"],
    }
