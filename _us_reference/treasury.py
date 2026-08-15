"""美國財政部資料：FiscalData（TGA / MSPD / MTS）與 TreasuryDirect 拍賣結果。皆免金鑰。"""
from __future__ import annotations

from common import get_json

FD = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"


def _fd(path: str, fields: str, sort: str = "-record_date",
        size: int = 120, filt: str | None = None) -> list[dict]:
    params = {"fields": fields, "sort": sort, "page[size]": str(size)}
    if filt:
        params["filter"] = filt
    return get_json(f"{FD}/{path}", params).get("data", [])


def tga(m: dict) -> dict:
    """每日財政部現金餘額（TGA），單位由百萬換算為十億美元。"""
    rows = _fd("v1/accounting/dts/operating_cash_balance",
               "record_date,account_type,open_today_bal", size=400)
    hist = [{"date": r["record_date"], "value": float(r["open_today_bal"]) / 1000}
            for r in rows
            if "Treasury General Account (TGA) Opening Balance" in (r.get("account_type") or "")
            and r.get("open_today_bal") not in (None, "", "null")]
    hist.reverse()
    if not hist:
        return {"ok": False, "reason": "DTS 無 TGA 開盤餘額資料"}
    return {"ok": True, "value": hist[-1]["value"], "asof": hist[-1]["date"],
            "history": hist[-24:], "raw_latest": hist[-1]["value"], "freq": "D",
            "extras": {}, "also": {}, "source_label": "FiscalData DTS"}


def bills_share(m: dict) -> dict:
    """Bill 占已發行可市場交易債務的比重（MSPD Table 1）。"""
    rows = _fd("v1/debt/mspd/mspd_table_1",
               "record_date,security_type_desc,security_class_desc,debt_held_public_mil_amt",
               size=800)
    # 實地確認的結構：Bills 掛在 (Marketable, Bills)，
    # 但合計掛在 security_type_desc = 'Total Marketable'、class 為 '_'。
    by_date: dict[str, dict[str, float]] = {}
    for r in rows:
        v = r.get("debt_held_public_mil_amt")
        if v in (None, "", "null"):
            continue
        typ = (r.get("security_type_desc") or "").strip()
        cls = (r.get("security_class_desc") or "").strip()
        d = by_date.setdefault(r["record_date"], {})
        if typ == "Marketable" and cls == "Bills":
            d["bills"] = float(v)
        elif typ == "Total Marketable":
            d["total"] = float(v)

    hist = []
    for dt in sorted(by_date):
        parts = by_date[dt]
        total, bills = parts.get("total"), parts.get("bills")
        if not total or not bills:
            continue
        hist.append({"date": dt, "value": bills / total * 100})
    if not hist:
        return {"ok": False, "reason": "MSPD 未取得 Bills / Total Marketable 分類"}
    return {"ok": True, "value": hist[-1]["value"], "asof": hist[-1]["date"],
            "history": hist[-24:], "raw_latest": hist[-1]["value"], "freq": "M",
            "extras": {}, "also": {}, "source_label": "FiscalData MSPD"}


def mts(m: dict) -> dict:
    """月度財政收支：滾動 12 個月赤字（MTS Table 1 的當月盈餘/赤字），單位十億美元。"""
    # MTS Table 1 以「月份名稱」當分類（同一 record_date 底下列出整個會計年度各月），
    # 且 dfct_sur 欄位的符號慣例不直觀，因此改由收入 − 支出自行計算，單位由美元換算為十億。
    rows = _fd("v1/accounting/mts/mts_table_1",
               "record_date,classification_desc,current_month_gross_rcpt_amt,"
               "current_month_gross_outly_amt", size=900)
    MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"]

    picked: dict[str, float] = {}
    for r in rows:
        dt = r["record_date"]
        want = MONTH_NAMES[int(dt[5:7]) - 1]
        if (r.get("classification_desc") or "").strip() != want:
            continue
        rcpt, outly = r.get("current_month_gross_rcpt_amt"), r.get("current_month_gross_outly_amt")
        if rcpt in (None, "", "null") or outly in (None, "", "null"):
            continue
        picked.setdefault(dt, (float(rcpt) - float(outly)) / 1e9)

    hist = [{"date": d, "value": v} for d, v in sorted(picked.items())]
    if not hist:
        return {"ok": False, "reason": "MTS 未取得當月收入/支出欄位"}

    rolling = sum(h["value"] for h in hist[-12:]) if len(hist) >= 12 else None
    return {"ok": True, "value": hist[-1]["value"], "asof": hist[-1]["date"],
            "history": hist[-24:], "raw_latest": hist[-1]["value"], "freq": "M",
            "extras": {"滾動12個月": rolling}, "also": {}, "source_label": "FiscalData MTS"}


_AUCTION_CACHE: dict[str, list[dict]] = {}


def _auctioned(sec_type: str) -> list[dict]:
    """依證券型別抓拍賣紀錄，同一次 build 內快取——七張年期卡只打兩次 API。"""
    if sec_type not in _AUCTION_CACHE:
        _AUCTION_CACHE[sec_type] = get_json(
            "https://www.treasurydirect.gov/TA_WS/securities/auctioned",
            {"format": "json", "type": sec_type, "pagesize": "250"})
    return _AUCTION_CACHE[sec_type]


def auctions(m: dict) -> dict:
    """指定年期的最新標售結果（mapping 的 term，如 '7-Year'）。

    分桶用 originalSecurityTerm：增額發行（reopening）的 securityTerm 是剩餘年期
    （如 9-Year 10-Month），只有原始年期能把它歸回 10-Year。
    TIPS 在這支 API 的 securityType 一樣是 Note/Bond，得靠 tips 欄位排除，
    否則名目 10Y 卡會混進實質利率 2% 出頭的 TIPS 場次。
    """
    term = m.get("term", "")
    sec_type = "Bond" if term in ("20-Year", "30-Year") else "Note"
    rows = _auctioned(sec_type)
    # 只採計「結果已公布」的拍賣：僅有公告尚未開標的紀錄 highYield 為空，
    # 若不濾掉會抓到還沒成交的場次。
    coupons = [r for r in rows
               if (r.get("originalSecurityTerm") or r.get("securityTerm")) == term
               and r.get("tips") != "Yes"
               and r.get("auctionDate") and (r.get("highYield") or "").strip()]
    if not coupons:
        return {"ok": False, "reason": f"TreasuryDirect 無 {term} 標售紀錄"}
    coupons.sort(key=lambda r: r["auctionDate"], reverse=True)
    latest = coupons[0]

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    hist = []
    for r in reversed(coupons[:24]):
        btc = num(r.get("bidToCoverRatio"))
        if btc is not None:
            hist.append({"date": r["auctionDate"][:10], "value": btc})

    # indirectBidderAccepted 是「得標金額」不是占比（API 回的是美元）。
    # 市場慣用的間接投標占比＝間接得標 ÷ 總得標，要自己算，直接拿原欄位會
    # 在卡面顯示成 30,801,964,000%。
    def share(field: str) -> float | None:
        part, total = num(latest.get(field)), num(latest.get("totalAccepted"))
        return round(part / total * 100, 1) if part and total else None

    # 增額發行（reopening）的需求結構跟新券不同，卡面上標明才能比較
    kind = f"{latest.get('securityTerm')} {latest.get('securityType')}"
    if latest.get("securityTerm") != latest.get("originalSecurityTerm"):
        kind += "（增額發行）"

    # 標售規模（QRA 若宣布增/減額，第一個反映在實際數字上的地方就是這裡，
    # 不必等我手動去讀公告才更新）——跟同年期「上一場」比較，不分新發或增額，
    # 因為 Treasury 調整規模可能發生在任一場。
    offer_latest = num(latest.get("offeringAmount"))
    prior = coupons[1] if len(coupons) > 1 else None
    offer_prior = num(prior.get("offeringAmount")) if prior else None
    extras = {
        "券別": kind,
        "得標利率(%)": num(latest.get("highYield")),
        "間接投標占比(%)": share("indirectBidderAccepted"),
        "一級交易商占比(%)": share("primaryDealerAccepted"),
        "標售規模(十億美元)": round(offer_latest / 1e9, 1) if offer_latest else None,
    }
    if offer_latest is not None and offer_prior is not None:
        diff_bn = round((offer_latest - offer_prior) / 1e9, 1)
        if abs(diff_bn) >= 0.05:      # 濾掉浮點雜訊，只留真的調整過的場次
            extras["規模變動(十億美元)"] = diff_bn

    return {"ok": True,
            "value": num(latest.get("bidToCoverRatio")),
            "asof": latest["auctionDate"][:10],
            "history": hist,
            "raw_latest": num(latest.get("bidToCoverRatio")),
            "freq": "D",
            "extras": extras,
            "also": {},
            "source_label": "TreasuryDirect 拍賣查詢",
            "value_label": "bid-to-cover"}


HANDLERS = {
    "fiscaldata_dts": tga,
    "fiscaldata_mspd": bills_share,
    "fiscaldata_mts": mts,
    "treasurydirect_auctions": auctions,
}


def fetch(card_id: str, m: dict) -> dict:
    h = HANDLERS.get(m.get("api", ""))
    if not h:
        return {"ok": False, "reason": f"未知的 Treasury API 型別 {m.get('api')}"}
    return h(m)
