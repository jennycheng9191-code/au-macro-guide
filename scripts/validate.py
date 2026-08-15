"""三道關卡 —— 資料上架前的把關。

設計原則：壞掉時的行為是「保留上期值並亮黃燈」，不是「顯示錯的數字」。
對交易用途而言，沒有更新遠比更新成錯的安全。

  關卡 1  合理範圍   值必須落在該指標的歷史合理區間內（mapping.json 的 sanity）
  關卡 2  變動幅度   與上期的變動不得超過歷史變動標準差的 3 倍
  關卡 3  交叉驗證   新聞來源必須有兩個獨立來源抓到相同數字
                     （官方新聞稿原文如 prnewswire 屬第一手，不受此關卡限制——
                       要求官方數字再找二手來源背書反而是降級）

另外檢查資料新鮮度：超過 stale_days 未更新即亮黃燈。
"""
from __future__ import annotations

import statistics

from common import age_from_period_end

GREEN, YELLOW, GRAY = "green", "yellow", "gray"


def _gate_range(value: float, sanity: dict | None) -> str | None:
    if not sanity or value is None:
        return None
    lo, hi = sanity.get("min"), sanity.get("max")
    if lo is not None and value < lo:
        return f"低於合理下限 {lo}"
    if hi is not None and value > hi:
        return f"高於合理上限 {hi}"
    return None


def _gate_jump(value: float, history: list[dict]) -> str | None:
    """與上期比較的變動是否超過歷史變動標準差的 3 倍。"""
    if len(history) < 6 or value is None:
        return None
    vals = [h["value"] for h in history]
    diffs = [b - a for a, b in zip(vals, vals[1:])]
    if len(diffs) < 5:
        return None
    try:
        sd = statistics.pstdev(diffs[:-1]) if len(diffs) > 5 else statistics.pstdev(diffs)
    except statistics.StatisticsError:
        return None
    if sd <= 0:
        return None
    change = abs(value - vals[-2]) if len(vals) >= 2 else 0
    if change > 3 * sd:
        return f"單期變動 {change:.2f} 超過歷史波動的 3 倍（{3 * sd:.2f}）"
    return None


def _gate_cross_check(res: dict, source: str) -> str | None:
    if source != "news":
        return None
    if res.get("sources_found") is None:
        return None                        # 該卡不是走新聞抓取，沒有來源計數可驗
    found = res.get("sources_found", 0)
    if found < 2:
        return "只有單一新聞來源抓到，未達雙來源交叉驗證"
    if not res.get("cross_check_agree"):
        return "CNBC 與 AP 抓到的數字不一致"
    return None


def check(res: dict, m: dict) -> dict:
    """回傳 {status, notes[]}，並在需要時把 status 降級。"""
    notes: list[str] = []

    if not res.get("ok"):
        return {"status": GRAY, "notes": [res.get("reason", "未取得")]}

    value = res.get("value")
    if value is None:
        return {"status": GRAY, "notes": ["來源回傳空值"]}

    status = GREEN

    if (n := _gate_range(value, m.get("sanity"))):
        return {"status": GRAY, "notes": [f"關卡1 未過：{n}（不採用，保留上期值）"]}

    if (n := _gate_jump(value, res.get("history") or [])):
        status = YELLOW
        notes.append(f"關卡2：{n}")

    # 走備援時實際來源與 mapping 宣告的不同，關卡要跟著實際來源走
    actual_source = res.get("source_kind") or m.get("source", "")
    if (n := _gate_cross_check(res, actual_source)):
        status = YELLOW
        notes.append(f"關卡3：{n}")

    asof = res.get("asof") or ""
    if asof:
        age = age_from_period_end(asof, res.get("freq", "M"))
        limit = m.get("stale_days")
        if limit and age > limit:
            status = YELLOW
            notes.append(f"期別結束後已 {age} 天仍未更新（正常應在 {limit} 天內）")
        res["age_days"] = age
    else:
        status = YELLOW
        notes.append("來源未提供明確期別")

    return {"status": status, "notes": notes}
