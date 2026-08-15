"""ABS Data API（SDMX）抓取模組——本手冊 27 張卡的主力來源。

澳洲沒有 FRED 這種單一總匯 API，ABS 這支是最接近的替代：免金鑰、
涵蓋通膨／勞動／薪資／活動／房市大部分指標，且提供完整長序列。

要點（2026-08-15 實打驗證）：
  · 回傳格式指定 CSV（`application/vnd.sdmx.data+csv`）比 JSON 好解析太多，
    SDMX-JSON 的維度是索引編號，要另外拉 DSD 才看得懂。
  · **版本號會變動**（CPI 已升到 2.0.0）。mapping 不寫死版本，
    URL 用 `ABS,{dataflow}` 讓伺服器給最新版，避免升版就整張卡壞掉。
  · dataflow 動輒上萬條序列（BA_GCCSA 有 11 萬條），一定要用 SDMX key
    把範圍縮到單一序列，不可整包拉。
  · 兩個已停更的坑：`CPI_M` 凍結在 2025-09（月度與季度 CPI 現已合併進 `CPI`）、
    `RPPI` 凍結在 2021-Q4（替代品 `RES_DWELL_ST`，但口徑從指數變成均價）。
"""
from __future__ import annotations

import csv
import io

from common import get_text, transform

BASE = "https://data.api.abs.gov.au/rest/data/ABS"
ACCEPT_CSV = "application/vnd.sdmx.data+csv"

_cache: dict[str, list[dict]] = {}


def _url(dataflow: str, key: str, start: str | None) -> str:
    # key 空字串代表整個 dataflow；有 key 時才縮範圍
    u = f"{BASE},{dataflow}/{key or 'all'}"
    return f"{u}?startPeriod={start}" if start else u


def rows(dataflow: str, key: str = "", start: str | None = None) -> list[dict]:
    """抓一段 SDMX CSV 回來，轉成 dict 列表（欄名即維度名）。"""
    ck = f"{dataflow}|{key}|{start}"
    if ck in _cache:
        return _cache[ck]
    txt = get_text(_url(dataflow, key, start), headers={"Accept": ACCEPT_CSV})
    if txt.strip() == "NoRecordsFound":
        _cache[ck] = []
        return []
    out = list(csv.DictReader(io.StringIO(txt)))
    _cache[ck] = out
    return out


def _apply_filter(recs: list[dict], flt: dict | None) -> list[dict]:
    """mapping 的 filter 是安全網：key 選錯或 ABS 加了新維度時擋下來。

    ABS 偶爾會在 dataflow 裡新增維度，原本唯一的 key 就會突然回傳多條序列。
    沒有這道檢查的話，程式會默默拿其中一條（順序還不保證）當成正確答案。
    """
    if not flt:
        return recs
    return [r for r in recs
            if all(str(r.get(col, "")) == str(val) for col, val in flt.items())]


def _series(recs: list[dict]) -> list[dict]:
    """把同一條序列的觀測值整理成 [{date, value}]，由舊到新。"""
    obs = []
    for r in recs:
        v = (r.get("OBS_VALUE") or "").strip()
        p = (r.get("TIME_PERIOD") or "").strip()
        if not v or not p:
            continue
        try:
            obs.append({"date": _period_to_iso(p), "value": float(v)})
        except ValueError:
            continue
    obs.sort(key=lambda o: o["date"])
    return obs


def _period_to_iso(p: str) -> str:
    """ABS 期別轉 ISO 日期（期別起始日）。

    月頻 2026-06 → 2026-06-01
    季頻 2026-Q2 → 2026-04-01   （季別標成該季起始月，common.transform 的
                                  qoq 往回三個月才對得上上一季）
    年頻 2026    → 2026-01-01
    """
    p = p.strip()
    if "-Q" in p:
        y, q = p.split("-Q")
        return f"{int(y):04d}-{(int(q) - 1) * 3 + 1:02d}-01"
    if len(p) == 7 and p[4] == "-":
        return f"{p}-01"
    if len(p) == 4:
        return f"{p}-01-01"
    return p if len(p) == 10 else f"{p}-01"


def _freq_of(recs: list[dict]) -> str:
    fs = {(r.get("FREQ") or "").strip() for r in recs}
    fs.discard("")
    return fs.pop() if len(fs) == 1 else "M"


def _result(dataflow: str, key: str, flt: dict | None, display: str,
            start: str | None, label: str) -> dict:
    recs = _apply_filter(rows(dataflow, key, start), flt)
    if not recs:
        return {"ok": False, "reason": f"{dataflow} 依 key/filter 篩選後無資料"}

    # 篩到多條序列代表 key 或 filter 不夠精確——寧可失敗也不要隨便挑一條。
    # 錯誤訊息帶上實際的維度組合，除錯時不用重跑一次才知道差在哪。
    dims = {tuple(sorted((k, v) for k, v in r.items()
                         if k not in ("TIME_PERIOD", "OBS_VALUE", "OBS_STATUS",
                                      "OBS_COMMENT", "DECIMALS", "UNIT_MEASURE",
                                      "BASE_PERIOD", "DATAFLOW")))
            for r in recs}
    if len(dims) > 1:
        sample = [dict(d) for d in list(dims)[:3]]
        return {"ok": False,
                "reason": f"{dataflow} 篩出 {len(dims)} 條序列（需唯一），樣本：{sample}"}

    obs = _series(recs)
    if not obs:
        return {"ok": False, "reason": f"{dataflow} 無可用觀測值"}

    freq = _freq_of(recs)
    ser = transform(obs, display, freq)
    if not ser:
        return {"ok": False, "reason": f"{dataflow} 資料長度不足以計算 {display}"}

    return {
        "ok": True,
        "value": ser[-1]["value"],
        "asof": ser[-1]["date"],
        "history": ser[-24:],
        "raw_latest": obs[-1]["value"],
        "freq": freq,
        "source_label": label or f"ABS {dataflow}",
    }


def fetch(card_id: str, m: dict) -> dict:
    res = _result(m["dataflow"], m.get("key", ""), m.get("filter"),
                  m.get("display", "level"), m.get("start"),
                  m.get("source_label", ""))
    if not res["ok"]:
        return res

    # 附帶序列（子項／對照組），例如勞動力調查同時帶全職與兼職就業。
    # ABS 回的是完整浮點精度（失業率會是 4.42834371），一定要四捨五入——
    # extras 不會經過 build.fmt，原樣送進前端就是一串沒有意義的小數。
    extras: dict = {}
    for lab, spec in (m.get("extras") or {}).items():
        try:
            r = _result(spec.get("dataflow", m["dataflow"]), spec.get("key", ""),
                        spec.get("filter"), spec.get("display", "level"),
                        spec.get("start", m.get("start")), "")
            extras[lab] = (round(r["value"], spec.get("decimals", m.get("decimals", 1)))
                           if r["ok"] else None)
        except Exception:                               # noqa: BLE001
            extras[lab] = None
    res["extras"] = extras

    # 同一條序列的其他呈現形式（例如季度 CPI 同時給 QoQ 與 YoY）
    also: dict = {}
    for form in m.get("also", []):
        r = _result(m["dataflow"], m.get("key", ""), m.get("filter"),
                    form, m.get("start"), "")
        if r["ok"]:
            also[m.get("also_labels", {}).get(form, form)] = r["value"]
    res["also"] = also
    return res


def fetch_derived(card_id: str, m: dict) -> dict:
    """由多條 ABS 序列相減／相除得出的合成指標。

    method=diff  兩序列相減（如私部門 WPI 減公部門 WPI 的差距）
    """
    specs = m["inputs"]
    seqs = []
    for s in specs:
        recs = _apply_filter(rows(s.get("dataflow", ""), s.get("key", ""),
                                  s.get("start", m.get("start"))), s.get("filter"))
        o = _series(recs)
        if not o:
            return {"ok": False, "reason": f"{s.get('dataflow')} 無可用觀測值"}
        seqs.append({x["date"]: x["value"] for x in o})

    a, *rest = seqs
    common_dates = sorted(set(a).intersection(*[set(s) for s in rest]) if rest else a)
    if not common_dates:
        return {"ok": False, "reason": "各序列沒有共同期別"}

    hist = [{"date": d, "value": a[d] - sum(s[d] for s in rest)} for d in common_dates]
    return {
        "ok": True,
        "value": hist[-1]["value"],
        "asof": hist[-1]["date"],
        "history": hist[-24:],
        "raw_latest": hist[-1]["value"],
        "freq": m.get("freq", "Q"),
        "extras": {},
        "also": {},
        "source_label": m.get("source_label", "ABS 合成序列"),
    }
