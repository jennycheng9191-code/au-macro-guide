"""AOFM Data Hub 抓取模組——發債計畫、Treasury Notes、TIB、負債水位。

兩個必須知道的坑（2026-08-15 實測）：

1. **aofm.gov.au 有 Akamai 機器人偵測**，而且擋法是靜默丟棄不是回錯誤碼：
   TLS 握手會成功，然後伺服器再也不回應直到逾時。requests / urllib / httpx
   全數失敗，真實 Chrome 正常。走 `common.get_impersonated`（curl_cffi
   模擬 Chrome TLS 指紋）才通。

2. **檔案路徑帶日期資料夾且會變動**
   （`/sites/default/files/2025-08-20/issuance.csv`）。不可以把網址寫死在
   mapping 裡——每次要先抓 `/data-hub` 頁面，從 HTML 撈出當下的連結。
   `file_index()` 就是做這件事，build.py 會把結果快取給所有 AOFM 卡共用。

死路（不要再試）：data.gov.au 上的 AOFM 資料集只是把檔案連回 aofm.gov.au
（一樣被擋），而且 CKAN metadata 從 2024-05 就沒更新過。
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urljoin

from common import get_impersonated

BASE = "https://www.aofm.gov.au"
HUB = f"{BASE}/data-hub"


def file_index() -> dict[str, str]:
    """抓一次 data-hub，回傳 {正規化檔名: 絕對網址}。

    正規化＝去掉路徑與副檔名、小寫、非英數轉底線，這樣 mapping 只要寫
    `treasury_bonds_issuance` 這種穩定名字，日期資料夾怎麼變都對得上。
    """
    try:
        html = get_impersonated(HUB)
    except Exception as e:                              # noqa: BLE001
        print(f"  ! AOFM data-hub 取得失敗：{e}")
        return {}

    idx: dict[str, str] = {}
    for href in re.findall(r'href="([^"]+\.(?:csv|xlsx|xls))"', html, re.I):
        name = unquote(href.rsplit("/", 1)[-1])
        stem = re.sub(r"\.[a-z]+$", "", name, flags=re.I)
        # 檔名尾巴常帶 _0 / _1 這種 Drupal 重複上傳流水號，正規化時去掉
        norm = re.sub(r"_\d+$", "", re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_"))
        idx.setdefault(norm, urljoin(BASE, href))
    return idx


def fetch(card_id: str, m: dict, index: dict[str, str]) -> dict:
    key = m.get("file")
    if not key:
        return {"ok": False, "reason": "mapping 未指定 file"}
    url = index.get(key)
    if not url:
        near = [k for k in index if key.split("_")[0] in k][:5]
        return {"ok": False,
                "reason": f"data-hub 找不到檔案 {key}（相近的有 {near or '無'}）"}
    return {"ok": False, "reason": f"AOFM 解析器尚未實作（檔案已定位：{url}）"}
