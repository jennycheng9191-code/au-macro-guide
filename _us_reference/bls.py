"""BLS 官方公開 API（api.bls.gov）。

bls.gov 的網頁本身會擋自動化 User-Agent（403），但這支公開資料 API 是
另一條獨立管道，不受阻擋。公布當天比 FRED 鏡像更快拿到新值——2026-08-07
的教訓：FRED 的 PAYEMS 在 BLS 官方已公布 7 月非農近一小時後仍停在 6 月，
同一批數字打這支 API 已經是「latest": true」。

免金鑰但有查詢額度（未註冊每日 25 次、單次最多 25 條序列），這裡把同一支
序列的請求做 process 內快取，一次 build 對同一序列只打一次。
"""
from __future__ import annotations

from common import get_json, transform

BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data"
_obs_cache: dict[str, list[dict]] = {}
_MONTH_PERIODS = {f"M{i:02d}" for i in range(1, 13)}   # 排除 M13(年均) 等特殊 period


def observations(series_id: str, years_back: int = 4) -> list[dict]:
    """回傳由舊到新的 [{date, value}]，只取月頻資料。"""
    if series_id in _obs_cache:
        return _obs_cache[series_id]
    from datetime import date
    end_year = date.today().year
    d = get_json(f"{BASE}/{series_id}",
                 {"startyear": str(end_year - years_back), "endyear": str(end_year)})
    if d.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API 回報 {d.get('status')}：{'; '.join(d.get('message', []))}")
    series = d.get("Results", {}).get("series", [])
    obs = []
    if series:
        for item in series[0].get("data", []):
            period = item.get("period", "")
            if period not in _MONTH_PERIODS:
                continue
            try:
                val = float(item["value"])
            except (TypeError, ValueError):
                continue
            obs.append({"date": f"{item['year']}-{period[1:]}-01", "value": val})
    obs.sort(key=lambda o: o["date"])
    _obs_cache[series_id] = obs
    return obs


def _series_result(series_id: str, display: str) -> dict:
    obs = observations(series_id)
    if not obs:
        return {"ok": False, "reason": f"BLS 序列 {series_id} 無可用觀測值"}
    ser = transform(obs, display, "M")
    if not ser:
        return {"ok": False, "reason": f"{series_id} 資料長度不足以計算 {display}"}
    return {
        "ok": True,
        "value": ser[-1]["value"],
        "asof": ser[-1]["date"],
        "history": ser[-24:],
        "raw_latest": obs[-1]["value"],
        "freq": "M",
        "source_label": f"BLS API {series_id}",
    }


def fetch(card_id: str, m: dict) -> dict:
    res = _series_result(m["series"], m.get("display", "level"))
    if not res["ok"]:
        return res

    # 附帶序列（子項 / 對照組）——跟 fred.py 同樣的慣例
    extras: dict[str, float] = {}
    for label, sid in (m.get("extras") or {}).items():
        try:
            o = observations(sid)
            if o:
                extras[label] = o[-1]["value"]
        except Exception:                             # noqa: BLE001
            extras[label] = None
    res["extras"] = extras

    also: dict[str, float] = {}
    for form in m.get("also", []):
        r = _series_result(m["series"], form)
        if r["ok"]:
            also[m.get("also_labels", {}).get(form, form)] = r["value"]
    res["also"] = also
    return res
