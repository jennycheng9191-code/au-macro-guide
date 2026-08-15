# 澳洲總經指標手冊（自動更新版）

45 個澳洲總經指標的參考手冊，數值每天由 GitHub Actions 自動抓取官方來源更新。
姊妹站：[美國總經指標手冊](https://jennycheng9191-code.github.io/us-macro-guide/)。

## 資料來源

| 來源 | 卡數 | 說明 |
|:--|--:|:--|
| ABS Data API（SDMX） | 27 | 免金鑰。`data.api.abs.gov.au`，回 CSV 格式 |
| RBA 統計表 CSV | 3 | 固定檔名直連，無反爬 |
| AOFM Data Hub | 4 | ⚠️ 有 Akamai 機器人偵測，須用 `curl_cffi` 模擬 Chrome TLS 指紋 |
| 私人機構網頁 | 6 | PMI、NAB、Westpac、Cotality、HIA，只取新聞稿頭條數字 |
| 人工輸入 | 5 | 見 `data/manual.json` |

澳洲沒有 FRED 這種單一總匯 API，所以來源比美國那份分散得多。
各來源的取數細節與踩過的坑寫在 `scripts/sources/*.py` 的模組 docstring 裡。

## 兩件澳洲特有的事

**CPI 雙軌**：月度與季度 CPI 並存，兩者不可互相取代。
RBA 貨幣政策聲明與 SMP 引用的是**季度**數字，月度只提供更即時的方向。
季度 Trimmed Mean 與 Weighted Median 在 `CPI_Q` dataflow，
但季度 headline 總指數不在裡面，得從統一 `CPI` 的指數值自算年增率。

**MHSI 取代零售銷售**（2025/7 起）：媒體仍常寫成 retail sales，
查證時要回到 ABS 的 Monthly Household Spending Indicator。

## 本機執行

```bash
pip install -r requirements.txt
python scripts/build.py        # 抓取並組裝 data/latest.json
python scripts/test_transform.py
```

不需要任何 API 金鑰——ABS、RBA、AOFM 三條來源都是公開免金鑰的。

## 人工補值

把數字寫進 `data/manual.json`，人工值優先序最高：

```json
{
  "card_id": {"value": 1.2, "asof": "2026-06", "note": "判讀句", "by": "Jenny", "at": "2026-08-15"}
}
```

## 進度與待辦

見 `docs/progress.md`。
