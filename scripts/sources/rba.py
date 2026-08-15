"""RBA 統計表 CSV 抓取模組——現金利率、信貸成長、央行資產負債表。

RBA 這條是三條來源裡最穩的：檔名固定（`f1.1-data.csv` 這種表號命名，
不像 AOFM 帶日期資料夾會變），無反爬，且每張表都有 `Series ID` 標題列，
用序列代號定位比用欄位順序安全得多——RBA 會在表中間插新欄位。

⚠️ rba.gov.au 的**首頁**對程式化請求回 403，但 `/statistics/tables/csv/`
底下的檔案正常 200。不要因為首頁擋就以為整站不能抓。
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from common import get_text, transform

BASE = "https://www.rba.gov.au/statistics/tables/csv"

# RBA 各表的日期格式不統一，兩種都要吃
_DATE_FORMATS = ("%d/%m/%Y", "%d-%b-%Y")

_cache: dict[str, tuple[dict[str, int], list[list[str]], str]] = {}


def _parse_date(s: str) -> str | None:
    s = s.strip()
    for f in _DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            continue
    return None


def _load(table: str):
    """回傳 ({序列代號: 欄索引}, 資料列, 發布日)。"""
    if table in _cache:
        return _cache[table]

    txt = get_text(f"{BASE}/{table}-data.csv")
    rows = list(csv.reader(io.StringIO(txt)))

    cols: dict[str, int] = {}
    pub = ""
    data: list[list[str]] = []
    for r in rows:
        if not r:
            continue
        head = r[0].strip().lstrip("﻿")
        if head == "Series ID":
            cols = {c.strip(): i for i, c in enumerate(r) if i and c.strip()}
            continue
        if head == "Publication date":
            pub = next((c.strip() for c in r[1:] if c.strip()), "")
            continue
        # 標題區的其他列（Title / Description / Frequency / Type / Units / Source）
        # 一律跳過。資料列靠「第一欄解析得出日期」判斷，不能只認一種格式——
        # RBA 各表的日期格式不一致：D1/F1.1 是 31/07/2026，A1 是 03-Jul-2013。
        if cols and _parse_date(head):
            data.append(r)

    if not cols:
        raise RuntimeError(f"RBA {table} 找不到 Series ID 標題列")
    _cache[table] = (cols, data, pub)
    return _cache[table]


def observations(table: str, series: str) -> list[dict]:
    cols, data, _ = _load(table)
    if series not in cols:
        raise RuntimeError(f"RBA {table} 沒有序列 {series}（可用：{list(cols)[:8]}…）")
    i = cols[series]
    obs = []
    for r in data:
        if i >= len(r):
            continue
        v = r[i].strip()
        d = _parse_date(r[0])
        if not v or not d:
            continue
        try:
            obs.append({"date": d, "value": float(v)})
        except ValueError:
            continue
    obs.sort(key=lambda o: o["date"])
    return obs


def _freq_of(table: str, series: str) -> str:
    """從資料列的實際間隔推頻率，比讀 Frequency 標題列可靠。

    RBA 的 Frequency 列有些欄位寫 "See notes"（F1.1 的後幾欄就是），
    照那個字串走會拿到不存在的頻率碼。
    """
    obs = observations(table, series)
    if len(obs) < 3:
        return "M"
    d1 = datetime.fromisoformat(obs[-1]["date"])
    d2 = datetime.fromisoformat(obs[-2]["date"])
    gap = (d1 - d2).days
    return "D" if gap <= 3 else "W" if gap <= 10 else "M" if gap <= 45 else "Q"


def _result(table: str, series: str, display: str, label: str) -> dict:
    obs = observations(table, series)
    if not obs:
        return {"ok": False, "reason": f"RBA {table}/{series} 無可用觀測值"}
    freq = _freq_of(table, series)
    ser = transform(obs, display, freq)
    if not ser:
        return {"ok": False, "reason": f"RBA {table}/{series} 資料長度不足以計算 {display}"}
    return {
        "ok": True,
        "value": ser[-1]["value"],
        "asof": ser[-1]["date"],
        "history": ser[-24:],
        "raw_latest": obs[-1]["value"],
        "freq": freq,
        "source_label": label or f"RBA {table.upper()} {series}",
    }


def fetch(card_id: str, m: dict) -> dict:
    res = _result(m["table"], m["series"], m.get("display", "level"),
                  m.get("source_label", ""))
    if not res["ok"]:
        return res

    extras: dict = {}
    for lab, spec in (m.get("extras") or {}).items():
        try:
            o = observations(spec.get("table", m["table"]), spec["series"])
            extras[lab] = (round(o[-1]["value"], spec.get("decimals", m.get("decimals", 1)))
                           if o else None)
        except Exception:                               # noqa: BLE001
            extras[lab] = None
    res["extras"] = extras

    also: dict = {}
    for form in m.get("also", []):
        r = _result(m["table"], m["series"], form, "")
        if r["ok"]:
            also[m.get("also_labels", {}).get(form, form)] = r["value"]
    res["also"] = also
    return res
