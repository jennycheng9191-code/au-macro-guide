"""解析官方／機構網頁取數——PMI、NAB、Westpac、Cotality、HIA 等。

這幾家都是商業機構，紀律是**只取新聞稿裡已公開的頭條數字**，
不快取全文、不重製圖表（與美國那份處理 ISM 的標準一致）。

解析規則要錨在逐期固定重複的樣板字串（如 "(1985=100)" 這種標記），
不要綁死每期都會改寫的敘述句型——美國 CB 那張卡就是因為正則錨在
會變動的敘述上，抓到隔壁句的數字。
"""
from __future__ import annotations


def fetch(card_id: str, m: dict) -> dict:
    return {"ok": False, "reason": f"{card_id} 的網頁解析器尚未實作"}
