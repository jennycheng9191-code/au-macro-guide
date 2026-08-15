"""組裝 data/latest.json —— 網頁唯一讀取的資料檔。

流程：逐卡抓取 → 三道關卡驗證 → 規則判讀 → 寫檔。
任何一張卡失敗都不中斷整體流程，改為沿用上一版的值並亮燈。
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "sources")]

from common import DATA, load_env, read_json, write_json   # noqa: E402
import rules                                               # noqa: E402
import validate                                            # noqa: E402
from sources import abs_api, aofm, au_html, rba            # noqa: E402

TPE = timezone(timedelta(hours=8))


def _fetch_one(card_id: str, m: dict, ctx: dict) -> dict:
    src = m["source"]
    if src == "abs":
        return abs_api.fetch(card_id, m)
    if src == "abs_derived":
        return abs_api.fetch_derived(card_id, m)
    if src == "rba":
        return rba.fetch(card_id, m)
    if src == "aofm":
        # AOFM 的檔案路徑每次更新都會變，先抓一次 data-hub 索引全卡共用
        return aofm.fetch(card_id, m, ctx.setdefault("aofm_index", aofm.file_index()))
    if src == "html":
        return au_html.fetch(card_id, m)
    if src == "manual":
        return {"ok": False, "reason": "敘述性內容或來源被擋，依行事曆人工更新"}
    return {"ok": False, "reason": f"未知來源型別 {src}"}


def _apply_scale(res: dict, m: dict) -> dict:
    """單位換算（例如 FRED 的 Persons → 千人）。

    必須用「實際取數的那份 mapping」的 scale：不同來源的原始單位不一樣，
    拿主要來源的倍率去乘備援來源的值，會得到差三個數量級的錯誤數字。
    也必須在驗證之前套用，sanity 區間才會跟顯示單位一致。
    """
    if not (sc := m.get("scale")) or not res.get("ok"):
        return res
    if res.get("value") is not None:
        res["value"] *= sc
    if res.get("raw_latest") is not None:
        res["raw_latest"] *= sc
    res["history"] = [{"date": h["date"], "value": h["value"] * sc}
                      for h in res.get("history", [])]
    return res


def dispatch(card_id: str, m: dict, ctx: dict) -> dict:
    """主要來源失敗時，改試 mapping 裡宣告的備援來源。

    備援結果會標上 source_kind，validate 才知道要用備援來源的關卡規則
    （例如新聞來源仍須雙來源交叉驗證，不會因為掛在官方卡下就免驗）。
    """
    res = _apply_scale(_fetch_one(card_id, m, ctx), m)
    fb = m.get("fallback")
    if res.get("ok") or not fb:
        return res

    effective = {**m, **fb}
    try:
        alt = _apply_scale(_fetch_one(card_id, effective, ctx), effective)
    except Exception as e:                                      # noqa: BLE001
        print(f"  ! {card_id} 備援來源也失敗：{e}", file=sys.stderr)
        return res
    if not alt.get("ok"):
        return res

    alt["source_kind"] = fb["source"]
    alt["source_label"] = f"{alt.get('source_label') or fb['source']}（備援）"
    alt["fallback_note"] = f"主要來源未取得（{res.get('reason', '—')}），改用備援來源"
    return alt


def fmt(value, m: dict) -> str:
    if value is None:
        return "—"
    d = m.get("decimals", 1)
    unit = m.get("unit", "")
    s = f"{value:,.{d}f}"
    return f"{s}{unit}" if unit and unit != "%" else (f"{s}%" if unit == "%" else s)


def main() -> int:
    load_env()
    indicators = read_json(DATA / "indicators.json", [])
    mapping = read_json(DATA / "mapping.json", {})
    mapping.pop("_doc", None)
    manual = read_json(DATA / "manual.json", {})
    previous = read_json(DATA / "latest.json", {}).get("cards", {})
    # 官方不提供免費歷史API的卡（目前只有CB兩張）靠這裡自己累積——
    # 每次 build 把當月值 upsert 進去，久了自然長出走勢圖
    scraped_hist = read_json(DATA / "scraped_history.json", {})

    today = datetime.now(TPE).strftime("%Y-%m-%d")

    ctx: dict = {}
    cards: dict[str, dict] = {}
    tally = {"green": 0, "yellow": 0, "gray": 0}

    for card in indicators:
        cid = card["id"]
        m = mapping.get(cid)
        if not m:
            continue

        try:
            res = dispatch(cid, m, ctx)
        except Exception as e:                                  # noqa: BLE001
            res = {"ok": False, "reason": f"抓取例外：{e}"}
            print(f"  ! {card['n']}: {e}", file=sys.stderr)
            traceback.print_exc(limit=1, file=sys.stderr)

        # 官方不提供免費歷史API的卡（目前CB兩張）靠這裡自己累積歷史。
        # 候選值先併進 res["history"] 讓下面的關卡2（單期變動）也能套用，
        # 但要等關卡1（合理區間）確認過關才真的寫回持久化檔案——
        # 不然一次髒資料就永久污染了辛苦累積的歷史。
        pending_hist = None
        if m.get("persist_history") and res.get("ok") and res.get("asof"):
            pending_hist = [dict(e) for e in scraped_hist.get(cid, [])]
            existing = next((e for e in pending_hist if e["date"] == res["asof"]), None)
            if existing:
                existing["value"] = res["value"]      # 同月修正值，就地更新不重複累加
            else:
                pending_hist.append({"date": res["asof"], "value": res["value"]})
            pending_hist.sort(key=lambda h: h["date"])
            res["history"] = pending_hist[-24:]

        verdict = validate.check(res, m)
        status, notes = verdict["status"], list(verdict["notes"])

        if pending_hist is not None and status != "gray":
            scraped_hist[cid] = pending_hist

        # 走備援來源代表主要來源當下是壞的——即使數字通過關卡也要讓你看得見
        if res.get("fallback_note"):
            notes.insert(0, res["fallback_note"])
            status = "yellow" if status == "green" else status

        # 人工確認值最優先（你貼的數字或 TradingView 截圖）
        if cid in manual:
            man = manual[cid]
            res = {"ok": True, "value": man.get("value"), "asof": man.get("asof", ""),
                   "history": res.get("history", []) if res.get("ok") else [],
                   "extras": man.get("extras", {}), "also": {},
                   "value_label": man.get("value_label", ""),
                   "source_label": "人工輸入", "raw_latest": man.get("value")}
            status, notes = "green", [f"人工確認值（{man.get('by', 'Jenny')} 於 {man.get('at', '—')}）"]

        # 抓不到就沿用上一版，並明確標示
        elif status == "gray" and cid in previous and previous[cid].get("value") is not None:
            old = previous[cid]
            notes.append(f"本次未取得，沿用 {old.get('asof', '—')} 的前值")
            res = {"ok": True, "value": old["value"], "asof": old.get("asof", ""),
                   "history": old.get("history", []), "extras": old.get("extras", {}),
                   "also": old.get("also", {}), "source_label": old.get("source_label", ""),
                   "raw_latest": old.get("value")}
            status = "yellow"

        # 值的說明標籤。三個來源依序疊上去，人工值最優先：
        #   1. mapping 的 value_label（口徑說明，如「季度 · 年增率（RBA 正式引用版）」）
        #   2. label_as=quarter 補上季別（觀測日期是季別起始月，2026-Q2 標成 2026-04，
        #      不標會被誤讀成月度資料）
        #   3. 人工值自己帶的 value_label 蓋過前兩者
        #
        # 這裡不可以照抄美國版寫成「Q2 預測值」——那是 GDPNow 那張預測卡專用的，
        # 澳洲這批季頻卡是 ABS 實際公布的數字，標成預測值是錯的。
        if not (cid in manual and manual[cid].get("value_label")):
            label = m.get("value_label", "")
            if m.get("label_as") == "quarter" and res.get("asof"):
                y, mo = res["asof"][:4], int(res["asof"][5:7])
                q = f"{y} Q{(mo - 1) // 3 + 1}"
                label = f"{q}　{label}" if label else q
            if label:
                res["value_label"] = label

        # 灰燈代表這個值不可信（沒抓到，或沒過關卡 1）。值必須清掉——
        # 留著的話前端只要有一處照著 value 渲染，就會把被擋下的錯誤數字顯示出來。
        if status == "gray":
            res = {"ok": False, "asof": "", "history": [], "extras": {}, "also": {},
                   "source_label": res.get("source_label", "")}

        # QRA 這類敘述性事件卡沒有時間序列可套規則，規則引擎必然留白——
        # 人工填的判讀句要能覆蓋過去，不是被空字串蓋掉。
        if cid in manual and manual[cid].get("note"):
            note = manual[cid]["note"]
        else:
            note = rules.build_note(res, m) if res.get("ok") else ""
        tally[status] = tally.get(status, 0) + 1

        # new_since = 這張卡的「期別」最後一次往前推進的日期，供前端標 🆕。
        # 只在前一版已有期別、且期別確實變了才記——首次建置時整頁都會是新的，
        # 那樣標記沒有資訊量。抓不到值的卡不標。
        #
        # 用 stale_days 當頻率代理值：<10 的是日頻（本手冊為純總經導向，
        # 目前沒有日頻卡，但保留這條規則避免日後新增時天天掛 🆕）；
        # >=10 的月頻以上（月頻 40+、季頻 100+）才是「今天有新東西公布」。
        prev = previous.get(cid, {})
        new_since = prev.get("new_since", "")
        if (m.get("stale_days") or 0) >= 10:
            if (a := res.get("asof")) and prev.get("asof") and a != prev["asof"]:
                new_since = today

        cards[cid] = {
            "value": res.get("value"),
            "value_fmt": fmt(res.get("value"), m) if res.get("ok") else "—",
            "value_label": res.get("value_label", ""),
            "asof": res.get("asof", ""),
            "asof_label": res.get("asof_label", ""),
            "age_days": res.get("age_days"),
            "new_since": new_since,
            "history": res.get("history", []),
            "extras": {k: v for k, v in (res.get("extras") or {}).items() if v is not None},
            "also": res.get("also", {}),
            "status": status,
            "notes": notes,
            "note": note,
            "source_label": res.get("source_label", ""),
            "unit": m.get("unit", ""),
            "display": m.get("display", "level"),
            # 值上升對債市的意義：1=利空（殖利率上行壓力）、-1=利多、缺=語義不明確。
            # 刻意不叫 bond——indicators.json 的 bond 是「債市含義」的敘述文字，
            # 兩者同名不同物，前端一個讀 d.bond 一個讀 c.bond_dir，很容易混。
            "bond_dir": m.get("bond_dir"),
        }
        flag = {"green": "OK", "yellow": "!!", "gray": "--"}[status]
        print(f"  [{flag}] {card['n']:<22} {cards[cid]['value_fmt']:>14}  {res.get('asof', '')}")

    out = {
        "build_time": datetime.now(TPE).strftime("%Y-%m-%d %H:%M"),
        "summary": tally,
        "cards": cards,
    }
    write_json(DATA / "latest.json", out)
    write_json(DATA / "scraped_history.json", scraped_hist)
    print(f"\n完成：綠燈 {tally['green']} / 黃燈 {tally['yellow']} / 未取得 {tally['gray']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
