"""一次性工具：從 Wayback Machine 回填 Conference Board 兩張卡的歷史值。

CB 不提供免費歷史 API（完整序列是收費授權資料，官網新聞稿只給當月頭條），
所以往前的月份改用 web.archive.org 保存的舊快照，逐月重新解析同一頁面。
只需要跑一次；跑完歷史就進了 data/scraped_history.json，
之後每次 build.py 正常執行會自己往後累加，不必再跑這支腳本。

用法：python scripts/backfill_cb_history.py [月數，預設24]
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "sources")]

from common import DATA, get_json, get_text, read_json, write_json   # noqa: E402
from sources.html_src import _plain, parse_cb_page                    # noqa: E402

URL = "https://www.conference-board.org/topics/consumer-confidence"
CDX = "https://web.archive.org/cdx/search/cdx"


def _cdx_snapshots(months_back: int) -> list[str]:
    """回傳每個月一個快照 timestamp（該月最後一筆可用快照，較可能是當月報告發布後）。"""
    start = (date.today().replace(day=1) - timedelta(days=months_back * 31)).strftime("%Y%m")
    d = get_json(CDX, {"url": "conference-board.org/topics/consumer-confidence",
                        "output": "json", "from": start, "filter": "statuscode:200",
                        "collapse": "timestamp:6"})   # 同一天只留一筆
    if not d or len(d) < 2:
        return []
    rows = d[1:]   # 第一列是欄位標頭
    by_month: dict[str, str] = {}
    for row in rows:
        ts = row[1]                       # yyyymmddhhmmss
        by_month[ts[:6]] = ts             # 保留該月最晚的一筆（rows 是舊到新）
    return sorted(by_month.values())


def _fetch_snapshot(ts: str, retries: int = 3) -> str | None:
    url = f"https://web.archive.org/web/{ts}id_/{URL}"
    for attempt in range(retries):
        try:
            return get_text(url, retries=1)
        except Exception as e:                       # noqa: BLE001
            print(f"    重試 {attempt+1}/{retries}：{e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None


def main() -> int:
    months_back = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    print(f"查詢 Wayback 快照清單（近 {months_back} 個月）...")
    snapshots = _cdx_snapshots(months_back)
    print(f"找到 {len(snapshots)} 個候選快照")

    hist = read_json(DATA / "scraped_history.json", {})
    cci = {e["date"]: e["value"] for e in hist.get("conference_board_consumer_confidence", [])}
    diff = {e["date"]: e["value"] for e in hist.get("cb_labor_market_differential", [])}

    got_months: set[str] = set()
    for ts in snapshots:
        html = _fetch_snapshot(ts)
        if not html:
            print(f"  {ts}: 抓取失敗，略過")
            continue
        p = parse_cb_page(_plain(html))
        if not p:
            print(f"  {ts}: 頁面比對不到數字，略過")
            continue
        if p["asof"] in got_months:
            continue   # 同一個月已經有更早的快照抓到過，不重複印
        got_months.add(p["asof"])
        cci[p["asof"]] = p["cci"]
        if p["differential"] is not None:
            diff[p["asof"]] = p["differential"]
        print(f"  {ts} → {p['asof']}：CCI={p['cci']}"
              + (f"，差值={p['differential']}" if p["differential"] is not None else "，差值缺"))
        time.sleep(0.5)   # 對 archive.org 客氣一點

    hist["conference_board_consumer_confidence"] = [
        {"date": d, "value": v} for d, v in sorted(cci.items())]
    hist["cb_labor_market_differential"] = [
        {"date": d, "value": v} for d, v in sorted(diff.items())]
    write_json(DATA / "scraped_history.json", hist)
    print(f"\n完成：CCI {len(cci)} 個月、勞動差值 {len(diff)} 個月，已寫入 scraped_history.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
