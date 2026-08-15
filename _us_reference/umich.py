"""密西根大學消費者調查官方資料表。

為什麼不用 FRED：FRED 的 UMCSENT / MICH 會落後密大官網一期
（2026-08-02 實測：FRED 停在 6 月，密大官網已有 7 月），
且 FRED 沒有 5–10 年期通膨預期序列——那正是本卡 read 欄位強調要看的。

官方 CSV（格式：Month,YYYY,值…）：
  tbmics.csv      消費者信心指數 ICS_ALL
  tbmpx1px5.csv   通膨預期 PX_MD(1年) / PX5_MD(5–10年)
"""
from __future__ import annotations

import csv
import io

from common import get_text

BASE = "http://www.sca.isr.umich.edu/files/"
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}


def _rows(filename: str) -> list[dict]:
    text = get_text(BASE + filename)
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        mi = MONTHS.get((r.get("Month") or "").strip())
        yr = (r.get("YYYY") or "").strip()
        if not mi or not yr.isdigit():
            continue
        r["_date"] = f"{yr}-{mi:02d}-01"
        out.append(r)
    out.sort(key=lambda r: r["_date"])
    return out


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def sentiment(m: dict) -> dict:
    rows = [r for r in _rows("tbmics.csv") if _num(r.get("ICS_ALL")) is not None]
    if not rows:
        return {"ok": False, "reason": "密大信心 CSV 未解析出資料"}
    hist = [{"date": r["_date"], "value": _num(r["ICS_ALL"])} for r in rows]
    return {"ok": True, "value": hist[-1]["value"], "asof": hist[-1]["date"],
            "history": hist[-24:], "raw_latest": hist[-1]["value"], "freq": "M",
            "extras": {}, "also": {}, "source_label": "密大官方資料表 tbmics.csv"}


def inflation_expectations(m: dict) -> dict:
    rows = [r for r in _rows("tbmpx1px5.csv") if _num(r.get("PX_MD")) is not None]
    if not rows:
        return {"ok": False, "reason": "密大通膨預期 CSV 未解析出資料"}
    hist = [{"date": r["_date"], "value": _num(r["PX_MD"])} for r in rows]
    five = _num(rows[-1].get("PX5_MD"))
    return {"ok": True, "value": hist[-1]["value"], "asof": hist[-1]["date"],
            "history": hist[-24:], "raw_latest": hist[-1]["value"], "freq": "M",
            "extras": {"5–10年期": five}, "also": {},
            "source_label": "密大官方資料表 tbmpx1px5.csv",
            "value_label": "1年期中位數"}


HANDLERS = {"sentiment": sentiment, "inflation_expectations": inflation_expectations}


def fetch(card_id: str, m: dict) -> dict:
    h = HANDLERS.get(m.get("table", ""))
    if not h:
        return {"ok": False, "reason": f"未知的密大資料表型別 {m.get('table')}"}
    return h(m)
