"""新聞來源抓取：ISM 六張卡與 ADP。

背景：ISM 官網為 reCAPTCHA 牆、ADP 官網為 JS 外殼，兩者皆無法直接解析
（2026-08-02 實測）。因此改從 CNBC 與 AP 兩個獨立來源抓取，
並交由 validate.py 的三道關卡把關——抓不準時寧可不更新，也不給錯的數字。

抽取策略刻意保守：只接受「指標名稱 + 動詞 + 數字」這種明確語境，
不接受單純出現在句子裡的數字，以避開預期值、前值、分項數字的誤抓。
"""
from __future__ import annotations

import re

from common import get_text

CNBC_RSS = "https://www.cnbc.com/id/20910258/device/rss/rss.html"
AP_HUB = "https://apnews.com/hub/economy"

# 明確表示「本期讀值」的動詞，排除 expected / forecast / previous 等語境
VERB = r"(?:registered|came in at|was|stood at|hit|reached|fell to|dropped to|declined to|slipped to|eased to|rose to|climbed to|increased to|jumped to|improved to|edged (?:up|down) to|held at|remained at|posted|of)"

# 排除語境：這些字出現在數字前面代表不是本期實際值
EXCLUDE_BEFORE = re.compile(
    r"(?:expect\w*|forecast\w*|estimat\w*|consensus|survey\w*|poll\w*|"
    r"previous\w*|prior|last month'?s?|compared (?:with|to)|versus|vs\.?|"
    r"down from|up from|revised)\W{0,20}$", re.I)

# 注意：中間段一律用 [\s\S] 而非 [^.]。新聞句子裡經常夾帶「down from 49.5」
# 這種帶小數點的數字，用 [^.] 會在小數點處提前截斷而漏抓。
PATTERNS: dict[str, list[str]] = {
    "ism_manufacturing_pmi": [
        r"(?:ISM|Institute for Supply Management)[\s\S]{0,90}?manufacturing[\s\S]{0,60}?(?:PMI|index)\D{0,25}" + VERB + r"\s+(\d{2}\.\d)",
        r"manufacturing (?:PMI|index)\D{0,25}" + VERB + r"\s+(\d{2}\.\d)[\s\S]{0,80}?(?:ISM|Institute for Supply Management)",
    ],
    "ism_services_pmi": [
        r"(?:ISM|Institute for Supply Management)[\s\S]{0,90}?(?:services|non-?manufacturing)[\s\S]{0,60}?(?:PMI|index)\D{0,25}" + VERB + r"\s+(\d{2}\.\d)",
        r"services (?:PMI|index)\D{0,25}" + VERB + r"\s+(\d{2}\.\d)[\s\S]{0,80}?(?:ISM|Institute for Supply Management)",
    ],
    "ism_mfg_new_orders": [
        r"new orders (?:sub)?index\D{0,25}" + VERB + r"\s+(\d{2}\.\d)",
    ],
    "ism_mfg_prices_paid": [
        r"prices (?:paid )?(?:sub)?index\D{0,25}" + VERB + r"\s+(\d{2}\.\d)",
    ],
    "ism_manufacturing_employment": [
        r"manufacturing employment (?:sub)?index\D{0,25}" + VERB + r"\s+(\d{2}\.\d)",
        r"employment (?:sub)?index\D{0,25}" + VERB + r"\s+(\d{2}\.\d)[\s\S]{0,90}?manufactur",
    ],
    "ism_services_employment": [
        r"services employment (?:sub)?index\D{0,25}" + VERB + r"\s+(\d{2}\.\d)",
        r"employment (?:sub)?index\D{0,25}" + VERB + r"\s+(\d{2}\.\d)[\s\S]{0,90}?services",
    ],
    "adp_national_employment_report": [
        r"ADP[\s\S]{0,120}?private (?:sector )?(?:payrolls?|employment|jobs)[\s\S]{0,40}?(?:by |of |added |increased |rose |grew |fell |declined )(\d{1,3}(?:,\d{3})?)(?:,000)?\b",
        r"private (?:sector )?(?:payrolls?|employers?)[\s\S]{0,60}?(?:added|shed|cut)\s+(\d{1,3}(?:,\d{3})?)(?:,000)?[\s\S]{0,90}?ADP",
    ],
}


def _plain(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#x27;", "'")
    return re.sub(r"\s+", " ", html)


def _article_urls() -> list[str]:
    urls: list[str] = []
    try:
        rss = get_text(CNBC_RSS)
        urls += re.findall(r"<link>(https://www\.cnbc\.com/\d{4}/\d{2}/\d{2}/[^<]+)</link>", rss)
    except Exception:                                  # noqa: BLE001
        pass
    try:
        hub = get_text(AP_HUB)
        found = re.findall(r'href="(/article/[^"]+)"', hub)
        urls += ["https://apnews.com" + u for u in dict.fromkeys(found)][:25]
    except Exception:                                  # noqa: BLE001
        pass
    return list(dict.fromkeys(urls))[:40]


_page_cache: dict[str, str] = {}


def _page(url: str) -> str:
    if url not in _page_cache:
        try:
            _page_cache[url] = _plain(get_text(url))
        except Exception:                              # noqa: BLE001
            _page_cache[url] = ""
    return _page_cache[url]


def _domain(url: str) -> str:
    return "CNBC" if "cnbc.com" in url else "AP" if "apnews.com" in url else "其他"


def _extract(text: str, card_id: str) -> float | None:
    for pat in PATTERNS.get(card_id, []):
        for mo in re.finditer(pat, text, re.I):
            before = text[max(0, mo.start() - 60):mo.start(1)]
            if EXCLUDE_BEFORE.search(before):
                continue                                # 命中排除語境（預期值/前值）
            raw = mo.group(1).replace(",", "")
            try:
                v = float(raw)
            except ValueError:
                continue
            # ADP 卡的單位是千人，新聞寫的是人數（「added 104,000 jobs」）。
            # 不換算的話值會差 1000 倍，直接被關卡 1 的合理區間擋掉。
            return v / 1000 if card_id == "adp_national_employment_report" else v
    return None


def fetch(card_id: str, m: dict, urls: list[str] | None = None) -> dict:
    urls = urls if urls is not None else _article_urls()
    hits: dict[str, float] = {}          # 來源 -> 數值（每個來源取第一個命中）
    evidence: list[str] = []

    for u in urls:
        src = _domain(u)
        if src in hits:
            continue
        v = _extract(_page(u), card_id)
        if v is not None:
            hits[src] = v
            evidence.append(f"{src}: {v} ({u})")

    if not hits:
        return {"ok": False, "reason": "CNBC 與 AP 皆未抓到可辨識的數值",
                "sources_found": 0}

    values = list(hits.values())
    return {
        "ok": True,
        "value": values[0],
        "asof": "",                       # 期別由 build.py 依發布行事曆推定
        "history": [],
        "raw_latest": values[0],
        "freq": "M",
        "extras": {},
        "also": {},
        "source_label": " / ".join(hits.keys()),
        "sources_found": len(hits),
        "cross_check_agree": len(set(values)) == 1 and len(values) >= 2,
        "evidence": evidence,
    }
