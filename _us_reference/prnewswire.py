"""ISM 官方新聞稿抓取（經由 PR Newswire）。

背景：ISM 官網（ismworld.org）整站在 reCAPTCHA 與 SSO 登入牆後面——
任何路徑都只回 922 bytes 的 captcha 表單（2026-08-02、2026-08-04 兩次實測）。
但 ISM 每月的 Report On Business 新聞稿**全文**會同步發到 PR Newswire，
免費、無驗證碼、句式每月固定，且分項數字齊全（新訂單／物價／就業／生產…）。

相較於原本的 CNBC＋AP 二手轉述：
  - 這是官方原文，不是記者摘要
  - 記者只寫總指數，分項數字新聞通常不報；官方新聞稿一定有
  - 總指數的歷史值直接寫在新聞稿的網址裡（manufacturing-pmi-at-55-6-july-2026），
    抓總指數的 24 期歷史完全不需要下載內文

因此 ISM 六張卡改以本模組為主要來源，news.py 降為備援。
"""
from __future__ import annotations

import os
import re
import time

from common import get_text

ORG = "https://www.prnewswire.com/news/institute-for-supply-management/"
ORG_PAGES = 3                      # 每頁 100 筆，3 頁涵蓋 2020 年至今
SOURCE_LABEL = "ISM 官方新聞稿（PR Newswire）"

# 分項歷史需要逐篇下載內文，深度可用環境變數調整
SUBINDEX_DEPTH = int(os.environ.get("PRN_SUBINDEX_DEPTH", "24"))

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"], 1)}

# 例：/news-releases/manufacturing-pmi-at-55-6-july-2026-ism-manufacturing-pmi-report-302840669.html
#     /news-releases/services-pmi-at-54-june-2026-ism-services-pmi-report-302817275.html
# 開頭錨定 manufacturing|services，才不會抓到同樣格式的 hospital-pmi-at-...
SLUG = re.compile(
    r"/news-releases/(manufacturing|services)-pmi-at-"
    r"(\d{1,3}(?:-\d)?)-([a-z]+)-(\d{4})-[a-z0-9-]*\.html")

# 卡片 → (報告別, 內文分項標籤)。標籤為 None 代表總指數，直接取自網址。
CARDS: dict[str, tuple[str, str | None]] = {
    "ism_manufacturing_pmi":        ("manufacturing", None),
    "ism_services_pmi":             ("services", None),
    "ism_mfg_new_orders":           ("manufacturing", "New Orders Index"),
    "ism_mfg_prices_paid":          ("manufacturing", "Prices Index"),
    "ism_services_prices_paid":     ("services", "Prices Index"),
    "ism_manufacturing_employment": ("manufacturing", "Employment Index"),
    "ism_services_employment":      ("services", "Employment Index"),
}

# 「52.8 percent」與「51.2%」都要，「3.1 percentage points」不要——後者是變動量不是讀值。
#
# 必須認 % 符號：新聞稿最上方的分項小標寫成
#   「Business Activity Index at 55.4%; New Orders Index at 55.1%; Employment Index at 51.2%」
# 只認 percent 的話會略過小標，讓取值視窗滑進下一句，抓到總指數的數字
# （服務業就業曾因此被抓成 Services PMI 的 54.0，實際是 51.2）。
NUM = re.compile(r"(\d{1,3}(?:\.\d)?)\s*(?:%|percent\b(?!age))", re.I)

# 門檻描述不是讀值。服務業物價分項的開頭句是
#   「The Prices Index registered above 70 percent for the fourth time in five
#     months; the reading of 70.3 percent in July is...」
# 「標籤後第一個讀值」會拿到 above 後面的整數門檻 70.0，真值 70.3 在下一句。
# 製造業的句式沒有這種比較級開頭，所以這個陷阱到服務物價卡才踩到。
QUALIFIER = re.compile(
    r"(?:above|below|over|under|than|near|nearly|around|approximately)\s+\Z", re.I)


def _plain(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&reg;", "")
                .replace("&#x27;", "'").replace("&rsquo;", "'").replace("&mdash;", "—"))
    return re.sub(r"\s+", " ", html)


# ---------------------------------------------------------------- 發布索引

_index_cache: dict[str, list[dict]] | None = None


def _index() -> dict[str, list[dict]]:
    """回傳 {報告別: [{asof, value, url}]}，由新到舊。"""
    global _index_cache
    if _index_cache is not None:
        return _index_cache

    seen: dict[tuple[str, str], dict] = {}
    for page in range(1, ORG_PAGES + 1):
        try:
            html = get_text(f"{ORG}?page={page}&pagesize=100")
        except Exception:                                   # noqa: BLE001
            continue                                        # 單頁失敗只是歷史變短
        for mo in SLUG.finditer(html):
            kind, raw, month, year = mo.groups()
            mi = MONTHS.get(month)
            if not mi:
                continue
            asof = f"{year}-{mi:02d}-01"
            key = (kind, asof)
            if key not in seen:
                seen[key] = {"asof": asof, "value": float(raw.replace("-", ".")),
                             "url": "https://www.prnewswire.com" + mo.group(0)}

    out: dict[str, list[dict]] = {"manufacturing": [], "services": []}
    for (kind, _), rel in seen.items():
        out[kind].append(rel)
    for kind in out:
        out[kind].sort(key=lambda r: r["asof"], reverse=True)
    _index_cache = out
    return out


# ---------------------------------------------------------------- 內文分項

_body_cache: dict[str, str] = {}


def _body(url: str) -> str:
    if url not in _body_cache:
        try:
            _body_cache[url] = _plain(get_text(url))
            time.sleep(0.3)                                 # 對來源客氣一點
        except Exception:                                   # noqa: BLE001
            _body_cache[url] = ""
    return _body_cache[url]


def _subindex(text: str, label: str) -> float | None:
    """取標籤之後第一個「N percent」。

    ISM 新聞稿的句式固定，本期讀值一律出現在分項名稱之後、前值之前：
      「The New Orders Index ... registering 56.7 percent, up 0.7 percentage
        point compared to June's figure of 56 percent.」
      「The Employment Index reading of 52.8 percent is up 3.1 percentage points...」
    因此「標籤後的第一個讀值」就是本期值，不需要辨識動詞，
    只需跳過 QUALIFIER 那種「above N percent」的門檻描述。
    """
    window = 220      # 太長會滑進下一個分項的句子，抓到別人的數字
    for mo in re.finditer(re.escape(label), text, re.I):
        seg = text[mo.end():mo.end() + window]
        for hit in NUM.finditer(seg):
            if QUALIFIER.search(seg[:hit.start()]):
                continue
            return float(hit.group(1))
    return None


def _asof_label(asof: str) -> str:
    names = [m.capitalize() for m in MONTHS]
    return f"{asof[:4]} {names[int(asof[5:7]) - 1]}"


# ---------------------------------------------------------------- 對外介面

def fetch(card_id: str, m: dict) -> dict:
    spec = CARDS.get(card_id)
    if not spec:
        return {"ok": False, "reason": f"prnewswire 未定義卡片 {card_id}"}
    kind, label = spec

    releases = _index().get(kind, [])
    if not releases:
        return {"ok": False, "reason": "PR Newswire 的 ISM 發布索引未取得任何報告"}

    latest = releases[0]

    if label is None:
        # 總指數：數值與歷史全部來自網址，不需下載內文
        history = [{"date": r["asof"], "value": r["value"]}
                   for r in reversed(releases[:24])]
        value = latest["value"]
    else:
        history = []
        for r in releases[:SUBINDEX_DEPTH]:
            if (v := _subindex(_body(r["url"]), label)) is not None:
                history.append({"date": r["asof"], "value": v})
        history.sort(key=lambda h: h["date"])
        if not history or history[-1]["date"] != latest["asof"]:
            return {"ok": False,
                    "reason": f"最新一期新聞稿未解析出「{label}」讀值"}
        value = history[-1]["value"]

    return {
        "ok": True,
        "value": value,
        "asof": latest["asof"],
        "asof_label": _asof_label(latest["asof"]),
        "history": history,
        "raw_latest": value,
        "freq": "M",
        "extras": {},
        "also": {},
        "source_label": SOURCE_LABEL,
        "source_kind": "prnewswire",
        "evidence": [latest["url"]],
    }
