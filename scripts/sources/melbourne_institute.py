"""Melbourne Institute 消費者通膨預期——官方新聞頁的免費頭條數字。

## 2026-08-15／08-29 的「全站 403」是誤判

當時的結論是「melbourneinstitute.unimelb.edu.au 連根目錄都擋，curl_cffi 也不通」，
於是這張卡掛人工掛了三週。2026-09-06 重驗，真正的原因是**偽裝設定檔的名字**：

    requests（本站 UA）        403 ×5
    requests（Chrome UA）      403 ×4、200 ×1
    curl_cffi "chrome"         403 ×4、200 ×1      ← get_impersonated 原本寫死這個
    curl_cffi "chrome124"      200 ×5
    curl_cffi "chrome131"      200 ×5

`"chrome"` 是 curl_cffi 的**浮動別名**，Cloudflare 給它的 bot score 很差；
釘明確版本就穩定通過。設定檔現在統一在 `common.IMPERSONATE`。

同一次稽核還有第二個誤讀：試 `/publications/macro-reports` 拿到的是 **404**
（那個路徑根本不存在），不是 403——404 代表 WAF 其實已經放行了。
**403 與 404 要分開讀**，混在一起看會把「路徑錯」判成「站台擋死」。

## 解析錨點

發布頁是**常青網址**（每月覆蓋同一頁），所以網址可以寫死，不必像 ANZ 那樣去 hub 找：

    <h1 class="text-level-2">Consumer inflation expectations increased in August</h1>
    <p style="text-align:justify">The expected inflation rate (30-per-cent trimmed
    mean measure) rose by 0.2 percentage points in August to 4.9 per cent. …</p>
    <p …><strong>Next release:</strong> 11 am (AEST), Thursday 10 September 2026</p>

⚠️ **`<title>` 是壞的，絕對不能拿來判期別**：實測 2026-08 那期的 `<title>` 還寫著
「Consumer inflation expectations increase in February」——編輯改了 h1 沒改 title。
月份一律從內文（或 h1）取。

⚠️ **年份不在句子裡**。內文只寫月名，所以年份從「Next release」那句回推：
資料月必定在下次發布月之前，月號比它大就是去年（12 月的資料在 1 月發布）。

## 授權

`robots.txt` 只擋 `/support/`、`/fbearchive/`、`/sandbox/`，本頁允許抓取；
校方網站條款限「非商業用途」，無自動化存取禁令。完整報告與時間序列是**付費訂閱**，
所以這裡只取新聞頁上免費公開的頭條數字，不碰訂閱內容——與 ANZ／Westpac 兩張
私人機構卡的處理原則一致。歷史靠 build.py 的 persist_history 自行累積。
"""
from __future__ import annotations

import html as _html
import re

from common import IMPERSONATE, get_impersonated

NEWS = ("https://melbourneinstitute.unimelb.edu.au/news/news/macroeconomics/"
        "survey-of-consumer-inflationary-and-wage-expectations")

# Cloudflare 的 bot score 帶運氣成分：同一個設定檔多數時候 200，偶爾 403。
# 建置當天密集測試（一小時內約 20 次）之後就出現過整輪 403 的情況，
# 正式排程一天只打 3 次不至於這樣，但還是備幾個設定檔輪替，
# 一個被判定就換下一個。都失敗時 build.py 會沿用上一版的值並亮黃燈。
PROFILES = (IMPERSONATE, "chrome124", "chrome120", "chrome116")

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june",
     "july", "august", "september", "october", "november", "december"], 1)}

_MONTH_RE = "|".join(_MONTHS)

# 頭條句的三種寫法都要吃：升、降、持平
_VALUE_RE = re.compile(
    rf"\bin\s+({_MONTH_RE})\s+to\s+([\d.]+)\s+per\s+cent"          # …in August to 4.9 per cent
    rf"|\bto\s+([\d.]+)\s+per\s+cent\s+in\s+({_MONTH_RE})"          # …to 4.9 per cent in August
    rf"|\b(?:unchanged|remained|steady)\s+at\s+([\d.]+)\s+per\s+cent\s+in\s+({_MONTH_RE})",
    re.I)

_CHANGE_RE = re.compile(
    r"\b(rose|increased|lifted|fell|declined|decreased|dropped)\s+by\s+"
    r"([\d.]+)\s+percentage\s+points?", re.I)

_DOWN = {"fell", "declined", "decreased", "dropped"}

_NEXT_RE = re.compile(rf"Next release:.*?(\d{{1,2}})\s+({_MONTH_RE})\s+(\d{{4}})", re.I | re.S)


def _text(fragment: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ")


def _body(html: str) -> tuple[str, str]:
    """回傳（頭條段落純文字, h1 純文字）。"""
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    paras = [_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", html, re.S)]
    lead = next((p for p in paras
                 if re.search(r"expected inflation rate|trimmed mean", p, re.I)), "")
    return re.sub(r"\s+", " ", lead).strip(), re.sub(r"\s+", " ", _text(h1.group(1)) if h1 else "")


def _year_anchor(html: str) -> tuple[int, int]:
    """從「Next release」那句取（年, 月）。找不到就用 CMS 的發布戳記備援。"""
    if (m := _NEXT_RE.search(_text(html))):
        return int(m.group(3)), _MONTHS[m.group(2).lower()]
    # 備援：HTML 註解裡的 "Last published by: … on 20 Aug 2026 10:57am"
    if (m := re.search(rf"Last published by:.*?(\d{{1,2}})\s+([A-Za-z]{{3}})[a-z]*\s+(\d{{4}})",
                       html, re.I | re.S)):
        mon = next((v for k, v in _MONTHS.items() if k.startswith(m.group(2).lower())), None)
        if mon:
            return int(m.group(3)), mon
    raise RuntimeError("頁面上找不到「Next release」日期，無法判定年份")


def parse(html: str) -> dict:
    lead, h1 = _body(html)
    if not lead:
        raise RuntimeError("找不到含「expected inflation rate」的頭條段落")

    mm = _VALUE_RE.search(lead)
    if not mm:
        raise RuntimeError(f"頭條段落解不出數值：{lead[:140]}")
    month_name, value = (mm.group(1), mm.group(2)) if mm.group(1) else \
                        (mm.group(4), mm.group(3)) if mm.group(3) else \
                        (mm.group(6), mm.group(5))
    if not month_name and (hm := re.search(rf"\bin\s+({_MONTH_RE})\b", h1, re.I)):
        month_name = hm.group(1)          # 句子沒帶月份時退回 h1
    if not month_name:
        raise RuntimeError(f"解不出資料月份：{lead[:140]}｜{h1}")

    ny, nmo = _year_anchor(html)
    mon = _MONTHS[month_name.lower()]
    year = ny - 1 if mon > nmo else ny
    asof = f"{year:04d}-{mon:02d}-01"

    extras: dict = {}
    if (cm := _CHANGE_RE.search(lead)):
        delta = float(cm.group(2))
        if cm.group(1).lower() in _DOWN:
            delta = -delta
        extras["較前月（pp）"] = round(delta, 2)
        extras["前月值"] = round(float(value) - delta, 2)
    return {"value": float(value), "asof": asof, "extras": extras, "headline": h1}


def fetch(card_id: str, m: dict) -> dict:
    last = None
    html = None
    for prof in PROFILES:
        try:
            html = get_impersonated(NEWS, retries=2, profile=prof)
            break
        except Exception as e:                          # noqa: BLE001
            last = e
    if html is None:
        return {"ok": False, "reason": f"Melbourne Institute 取得失敗（{len(PROFILES)} 個設定檔全被擋）：{last}"}

    try:
        got = parse(html)
    except Exception as e:                              # noqa: BLE001
        return {"ok": False, "reason": f"Melbourne Institute 解析失敗：{e}"}

    return {
        "ok": True,
        "value": got["value"],
        "asof": got["asof"],
        "history": [],      # 免費頁只有當期，靠 build.py 的 persist_history 累積
        "raw_latest": got["value"],
        "freq": "M",
        "extras": got["extras"],
        "also": {},
        "source_label": m.get("source_label") or "Melbourne Institute 通膨預期",
    }
