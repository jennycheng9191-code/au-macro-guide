"""解析官方網頁 HTML：Conference Board 消費者信心、NAHB 建商信心。

兩者的數字都直接寫在新聞稿段落裡（2026-08-02 實測），
所以先把 HTML 標籤剝掉再用嚴格的語境正則抓，比解析 DOM 穩定。
"""
from __future__ import annotations

import re

from common import get_text

_text_cache: dict[str, str] = {}


def _cached_text(url: str) -> str:
    """CCI 卡與勞動差值卡同一頁，process 內快取避免同一次 build 打兩次。"""
    if url not in _text_cache:
        _text_cache[url] = _plain(get_text(url))
    return _text_cache[url]

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}


def _plain(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = (html.replace("&nbsp;", " ").replace("&mdash;", "—").replace("&reg;", "")
                .replace("&rsquo;", "'").replace("&ldquo;", '"').replace("&rdquo;", '"')
                .replace("&amp;", "&").replace("&ndash;", "–"))
    return re.sub(r"\s+", " ", html)


def _month_to_date(name: str, year: int | None = None) -> str:
    from datetime import date
    mi = MONTHS.get(name.capitalize())
    if not mi:
        return ""
    today = date.today()
    y = year or today.year
    if year is None and mi > today.month:       # 例如 12 月的報告在 1 月才讀到
        y -= 1
    return f"{y}-{mi:02d}-01"


def parse_cb_page(txt: str) -> dict | None:
    """解析 CB 消費者信心新聞稿全文，回傳這個月的所有可抽取數字。

    CB 的敘述句每月用字不同（rose/decreased/ticked up...），甚至跨年會整個
    改句型（2024年是「rose in July to 100.3 (1985=100)」，月份在數字前；
    2026年是「to 90.8 (1985=100) in July」，月份在後）——2026-08 為了回填
    Wayback歷史快照才發現這個坑，故意不綁死句子結構，只認兩個穩定錨點：
    「(1985=100)」前面緊接的數字＝指數值；「Updated: 星期, 月 日, 年」這行＝
    公布日期（可靠給出月份＋年份，比從敘述句猜月份精確，尤其12月報告在1月
    才讀到的跨年問題完全不用處理）。
    """
    val_m = re.search(r"([0-9]{2,3}\.[0-9])\s*\(1985=100\)", txt)
    date_m = re.search(r"Updated:\s*\w+,\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", txt)
    if not (val_m and date_m):
        return None
    month, year = date_m.group(1), int(date_m.group(3))
    mi = MONTHS.get(month.capitalize())
    if not mi:
        return None
    asof = f"{year}-{mi:02d}-01"

    def grab(label: str) -> float | None:
        mm = re.search(label + r"[\s\S]{0,240}?\b(?:to|at)\s+([0-9]{2,3}\.[0-9])", txt)
        return float(mm.group(1)) if mm else None

    def pct(word: str) -> float | None:
        mm = re.search(
            rf"([0-9]{{1,3}}\.[0-9])%\s+of consumers said jobs were[^0-9]{{0,20}}{word}",
            txt, re.IGNORECASE)
        return float(mm.group(1)) if mm else None

    # 錨在 "hard to get"— 這句固定樣板的收尾（每月逐字重複），往後一段距離內
    # 找第一個 N.N% —— 不能錨在「labor market differential」本身往後找 to/at，
    # 因為後面常緊接另一句「工作難找 rose to 22.5%」，用詞恰好也符合 to+數字+%，
    # 之前版本因此偶爾抓到下一句不相干的百分比（2026-08 回填時實測踩到這個坑）。
    diff_m = re.search(
        r'hard to get["\']*\s*[—–-]\s*[\s\S]{0,80}?([+-]?[0-9]{1,3}\.[0-9])\s*%',
        txt, re.IGNORECASE)
    plentiful, hard = pct("plentiful"), pct("hard to get")
    # 「差值」句子是2025年後才加進新聞稿的寫法，更早的月份沒有——退而求其次
    # 自己用兩個分項相減，官方兩個數字各自四捨五入，最多差0.1pp
    differential = float(diff_m.group(1)) if diff_m else (
        round(plentiful - hard, 1) if plentiful is not None and hard is not None else None)

    return {"asof": asof, "month": month, "cci": float(val_m.group(1)),
            "present": grab("Present Situation Index"), "expectations": grab("Expectations Index"),
            "plentiful": plentiful, "hard_to_get": hard, "differential": differential}


def conference_board(m: dict) -> dict:
    txt = _cached_text(m["url"])
    p = parse_cb_page(txt)
    if not p:
        return {"ok": False, "reason": "Conference Board 頁面未比對到信心指數敘述句"}
    return {"ok": True, "value": p["cci"], "asof": p["asof"],
            "asof_label": p["month"], "history": [],
            "raw_latest": p["cci"], "freq": "M",
            "extras": {"現況指數": p["present"], "預期指數": p["expectations"]},
            "also": {}, "source_label": "Conference Board 官網新聞稿"}


def labor_market_differential(m: dict) -> dict:
    """CB消費者信心調查的勞動子項：「工作充足」減「工作難找」。優先用 CB 自己
    算好的差值句子（比自行相減更貼近官方口徑），舊月份新聞稿沒有這句時
    才退回自算，見 parse_cb_page() 的說明。
    """
    txt = _cached_text(m["url"])
    p = parse_cb_page(txt)
    if not p or p["differential"] is None:
        return {"ok": False, "reason": "Conference Board 頁面未比對到勞動市場差值相關數字"}
    return {"ok": True, "value": p["differential"], "asof": p["asof"],
            "asof_label": p["month"], "history": [],
            "raw_latest": p["differential"], "freq": "M",
            "extras": {"工作充足(%)": p["plentiful"], "工作難找(%)": p["hard_to_get"]},
            "also": {}, "source_label": "Conference Board 官網新聞稿"}


def nahb(m: dict) -> dict:
    txt = _plain(get_text(m["url"]))

    period = re.search(r"HMI Key Findings:\s*([A-Za-z]+)\s+(\d{4})", txt)
    val = re.search(
        r"Builder confidence[\s\S]{0,180}?\b(?:to|at)\s+(\d{1,3})\s+in\s+[A-Z][a-z]+",
        txt)
    if not (period and val):
        return {"ok": False, "reason": "NAHB 頁面未比對到 HMI Key Findings 敘述句"}

    month, year = period.group(1), int(period.group(2))
    return {"ok": True, "value": float(val.group(1)),
            "asof": _month_to_date(month, year), "asof_label": f"{year} {month}",
            "history": [], "raw_latest": float(val.group(1)), "freq": "M",
            "extras": {}, "also": {}, "source_label": "NAHB 官網 HMI 頁"}


HANDLERS = {"confidence_index": conference_board, "hmi_key_findings": nahb,
            "labor_differential": labor_market_differential}


def fetch(card_id: str, m: dict) -> dict:
    h = HANDLERS.get(m.get("pattern", ""))
    if not h:
        return {"ok": False, "reason": f"未知的 HTML 解析型別 {m.get('pattern')}"}
    return h(m)
