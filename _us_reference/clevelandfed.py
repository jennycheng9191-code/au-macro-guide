"""Cleveland Fed 通膨即時預測（Inflation Nowcasting）。

官方圖表背後就是三支公開 JSON，免金鑰、無驗證碼（2026-08-04 實測）：
  nowcast_month.json  月增（MoM）
  nowcast_year.json   年增（YoY）
頁面本身是 JS 渲染，HTML 裡沒有數字，所以直接讀 JSON。

檔案結構：最外層是陣列，每個元素對應「一個被預測的目標月」，
element.chart.subcaption = "2026-7"，element.categories 是觀測日（預測做出的那天），
element.dataset 有 8 條序列——4 條 nowcast ＋ 4 條 Actual。

**Actual 序列只在該月數據正式公布後才有值**，這給了一個自我校正的選月規則：
第一個 Actual 還空著的月份，就是下一次要公布的月份。不必寫死行事曆，
也不會在公布日前後選錯月。CPI 與 PCE 的公布時程不同，各自用自己的 Actual 判斷。
"""
from __future__ import annotations

import re

from common import get_json

BASE = "https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting"
MONTH_URL = f"{BASE}/nowcast_month.json"
YEAR_URL = f"{BASE}/nowcast_year.json"

# 卡片 → (總指數序列名, 核心序列名)
CARDS: dict[str, tuple[str, str]] = {
    "cleveland_fed_cpi_nowcast": ("CPI Inflation", "Core CPI Inflation"),
    "cleveland_fed_pce_nowcast": ("PCE Inflation", "Core PCE Inflation"),
}

_cache: dict[str, list] = {}


def _load(url: str) -> list:
    if url not in _cache:
        _cache[url] = get_json(url)
    return _cache[url]


def _series(el: dict, name: str) -> list[dict]:
    for ds in el.get("dataset", []):
        if ds.get("seriesname") == name:
            return ds.get("data", [])
    return []


def _values(el: dict, name: str) -> list[float]:
    out = []
    for d in _series(el, name):
        v = d.get("value")
        if v not in (None, ""):
            try:
                out.append(float(v))
            except ValueError:
                continue
    return out


def _last(el: dict, name: str) -> float | None:
    vals = _values(el, name)
    return vals[-1] if vals else None


def _month_of(el: dict) -> tuple[int, int]:
    """subcaption "2026-7" → (2026, 7)。"""
    y, m = el["chart"]["subcaption"].split("-")
    return int(y), int(m)


def _observation_dates(el: dict, year: int, month: int) -> list[str]:
    """categories 的標籤是 "07/01" 這種沒有年份的日期。

    ⚠️ 裡面還混了事件標記（"CPI Jun"、"PCE Jun"——圖上標示前期數據公布日的
    垂直線），這些標記**不占資料點**：categories 有 27 個標籤但每條序列只有
    25 筆值，差的就是那 2 個標記。必須把非日期標籤整個濾掉再對齊，
    留空位會讓整條序列錯位，sparkline 的日期就全錯了。

    觀測日會延伸到目標月之後（預測 7 月的 nowcast 一路做到 8 月才停），
    所以月份小於目標月的那些屬於下一年——12 月的目標月會跨到隔年 1 月。
    """
    out = []
    for c in (el.get("categories") or [{}])[0].get("category", []):
        mo = re.fullmatch(r"(\d{2})/(\d{2})", str(c.get("label", "")).strip())
        if not mo:
            continue                        # 事件標記，不是觀測日
        mm, dd = int(mo.group(1)), int(mo.group(2))
        out.append(f"{year + (1 if mm < month else 0)}-{mm:02d}-{dd:02d}")
    return out


def _pick_target(arr: list, actual_name: str) -> tuple[dict | None, dict | None]:
    """回傳（下一個尚未公布的目標月, 最近一個已公布的目標月）。

    只認**檔尾那段連續**還沒有 Actual 的月份，不能從頭掃第一個空的——
    歷史區間中間也會有 Actual 空缺（2013-07 資料缺漏、2025-10 政府停擺期間
    未採集 CPI），從頭掃會選到十幾年前的月份。
    """
    prior, target_idx = None, None
    for i in range(len(arr) - 1, -1, -1):
        if _values(arr[i], actual_name):
            prior = arr[i]                  # 檔尾往回第一個已公布的月份
            break
        target_idx = i                       # 還沒公布，繼續往回找更早的
    return (arr[target_idx] if target_idx is not None else None), prior


def fetch(card_id: str, m: dict) -> dict:
    spec = CARDS.get(card_id)
    if not spec:
        return {"ok": False, "reason": f"clevelandfed 未定義卡片 {card_id}"}
    head, core = spec
    actual_core = f"Actual {core}"

    months, years = _load(MONTH_URL), _load(YEAR_URL)
    target, prior = _pick_target(months, actual_core)
    if target is None:
        return {"ok": False, "reason": "月增檔找不到尚未公布的目標月"}

    y, mo = _month_of(target)
    value = _last(target, core)
    if value is None:
        return {"ok": False, "reason": f"目標月 {y}-{mo:02d} 沒有 {core} 的預測值"}

    # 歷史＝這個月的 nowcast 逐日演變，看得出預測隨資料進來往哪飄
    dates = _observation_dates(target, y, mo)
    series = _series(target, core)
    history = []
    if len(dates) == len(series):
        for d, item in zip(dates, series):
            v = item.get("value")
            if v not in (None, ""):
                try:
                    history.append({"date": d, "value": float(v)})
                except ValueError:
                    continue
    else:
        # 對不齊就不猜——寧可沒有 sparkline，也不要標錯日期的走勢
        print(f"  ! {card_id} 觀測日 {len(dates)} 個對不上資料 {len(series)} 筆，略過歷史")
    asof = history[-1]["date"] if history else ""

    # 年增版：同一個目標月，從 year 檔取
    ytarget = next((el for el in years if _month_of(el) == (y, mo)), None)
    yoy_head = _last(ytarget, head) if ytarget else None
    yoy_core = _last(ytarget, core) if ytarget else None

    res = {
        "ok": True,
        "value": value,
        "asof": asof,
        "value_label": f"{y} 年 {mo} 月 預估",
        "history": history[-24:],
        "raw_latest": value,
        "freq": "D",
        "extras": {
            f"{head.split()[0]}月增": _last(target, head),
            f"{head.split()[0]}年增": yoy_head,
            f"核心{head.split()[0]}年增": yoy_core,
        },
        "also": {},
        "source_label": "Cleveland Fed 官方 JSON",
        "source_kind": "clevelandfed",
    }

    # 上期預測誤差——判斷這份 nowcast 現在準不準的唯一依據
    if prior is not None:
        py, pm = _month_of(prior)
        nc, act = _last(prior, core), _last(prior, actual_core)
        if nc is not None and act is not None:
            res["prior"] = {"month": f"{py}-{pm:02d}", "nowcast": nc, "actual": act}

    return res
