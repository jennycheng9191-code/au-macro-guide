# 47 卡資料來源對照清單

> 更新：2026-08-02　所有 FRED 序列代號皆經 API 驗證；數值已與手動查證版逐卡對照。
> `display` 欄決定卡片顯示原值或年增率／月變動——這是最容易與舊版對不起來的地方。

| # | 燈 | 指標 | 面向 | 來源 | 序列/端點 | 顯示 | 現值 | 期別 |
|--:|:--|:--|:--|:--|:--|:--|:--|:--|
| 1 | 🟢 | CPI 總指數 | 通膨 | fred | CPIAUCNS | yoy | 3.5% | 2026-06-01 |
| 2 | 🟢 | 核心CPI | 通膨 | fred | CPILFENS | yoy | 2.6% | 2026-06-01 |
| 3 | 🟢 | Super Core(核心服務ex住房) | 通膨 | fred | CUSR0000SASL2RS | yoy | 3.1% | 2026-06-01 |
| 4 | 🟢 | OER / 房租分項 | 通膨·房市 | fred | CUSR0000SEHC | yoy | 3.3% | 2026-06-01 |
| 5 | 🟢 | PCE / 核心PCE物價 | 通膨 | fred | PCEPILFE | yoy | 3.3% | 2026-06-01 |
| 6 | 🟢 | Trimmed Mean PCE | 通膨 | fred | PCETRIM12M159SFRBDAL | level | 2.23% | 2026-06-01 |
| 7 | 🟢 | PPI 生產者物價 | 通膨 | fred | PPIFIS | yoy | 5.5% | 2026-06-01 |
| 8 | 🟢 | 5y5y 通膨預期(遠期損益兩平) | 通膨·金融 | fred | T5YIFR | level | 2.30% | 2026-07-31 |
| 9 | 🟢 | NY Fed 消費者通膨預期 | 通膨 | nyfed_sce |  | level | 3.34% | 2026-06-01 |
| 10 | 🟢 | 密大通膨預期 | 通膨·信心 | umich | inflation_expectations | level | 4.2% | 2026-07-01 |
| 11 | 🟢 | 非農就業 NFP | 勞動 | fred | PAYEMS | mom_diff | 57千人 | 2026-06-01 |
| 12 | 🟢 | 失業率 | 勞動 | fred | UNRATE | level | 4.2% | 2026-06-01 |
| 13 | 🟢 | 勞動參與率 | 勞動 | fred | CIVPART | level | 61.5% | 2026-06-01 |
| 14 | 🟢 | 平均時薪 AHE | 勞動·薪資 | fred | CES0500000003 | yoy | 3.5% | 2026-06-01 |
| 15 | 🟢 | JOLTS 職缺 | 勞動 | fred | JTSJOL | level | 7,594千個 | 2026-05-01 |
| 16 | 🟢 | 初領失業金 | 勞動 | fred | ICSA | level | 197,000人 | 2026-07-25 |
| 17 | ⚪ | ADP 民間就業 | 勞動 | news | ADP private payrolls / ADP emp | mom_diff | — |  |
| 18 | ⚪ | ISM製造業就業分項 | 勞動·經濟活動 | news | ISM manufacturing employment | level | — |  |
| 19 | ⚪ | ISM服務業就業分項 | 勞動·經濟活動 | news | ISM services employment | level | — |  |
| 20 | 🟢 | ECI 僱傭成本指數 | 薪資 | fred | ECIALLCIV | yoy | 3.4% | 2026-04-01 |
| 21 | 🟢 | Atlanta Fed 薪資追蹤 | 薪資 | fred | FRBATLWGT3MMAUMHWGO | level | 3.6% | 2026-06-01 |
| 22 | ⚪ | ISM製造業PMI | 經濟活動 | news | ISM manufacturing PMI / manufa | level | — |  |
| 23 | ⚪ | ISM製造新訂單 | 經濟活動 | news | ISM manufacturing new orders | level | — |  |
| 24 | ⚪ | ISM製造物價分項 | 經濟活動·通膨 | news | ISM manufacturing prices paid  | level | — |  |
| 25 | ⚪ | ISM服務業PMI | 經濟活動 | news | ISM services PMI / services PM | level | — |  |
| 26 | 🟢 | 零售銷售 | 經濟活動 | fred | RSAFS | mom | 0.2% | 2026-06-01 |
| 27 | 🟢 | 工業生產 | 經濟活動 | fred | INDPRO | mom | 0.1% | 2026-06-01 |
| 28 | 🟢 | GDPNow | 經濟活動 | fred | GDPNOW | level | 5.0% | 2026-07-01 |
| 29 | 🟢 | 耐久財訂單 | 經濟活動 | fred | DGORDER | mom | 0.3% | 2026-06-01 |
| 30 | 🟢 | 密大消費者信心 | 信心 | umich | sentiment | level | 55.2 | 2026-07-01 |
| 31 | 🟢 | CB 消費者信心 | 信心·勞動 | html |  | level | 90.8 | 2026-07-01 |
| 32 | 🟢 | NAHB 建商信心 | 房市 | html |  | level | 34 | 2026-07-01 |
| 33 | 🟢 | 新屋開工 / 建照 | 房市 | fred | HOUST | level | 1,427千戶(年化) | 2026-06-01 |
| 34 | 🟢 | 成屋銷售 | 房市 | fred | EXHOSLUSM495S | level | 4,090千戶(年化) | 2026-06-01 |
| 35 | 🟢 | 新屋銷售 | 房市 | fred | HSN1F | level | 628千戶(年化) | 2026-06-01 |
| 36 | 🟢 | Case-Shiller 房價 | 房市 | fred | SPCS20RSA | yoy | 1.6% | 2026-05-01 |
| 37 | 🟢 | 30年期房貸利率 | 房市·金融 | fred | MORTGAGE30US | level | 6.66% | 2026-07-30 |
| 38 | ⚪ | QRA 季度再融資 | 財政 | manual |  | text | — |  |
| 39 | 🟢 | 附息債拍賣結果 | 財政 | treasury | treasurydirect_auctions | table | 2.5 | 2026-07-28 |
| 40 | 🟢 | TGA 財政部現金餘額 | 財政·金融 | treasury | fiscaldata_dts | level | 970十億美元 | 2026-07-30 |
| 41 | 🟢 | Bill 占比 | 財政 | treasury | fiscaldata_mspd | pct | 21.5% | 2026-06-30 |
| 42 | 🟢 | MTS 月度財政收支 | 財政 | treasury | fiscaldata_mts | level | -93十億美元 | 2026-06-30 |
| 43 | 🟢 | NFCI 金融條件指數 | 金融 | fred | NFCI | level | -0.55 | 2026-07-24 |
| 44 | 🟢 | SOFR-IORB 利差 | 金融 | derived | SOFR - IORB | level | 0.0bp | 2026-07-30 |
| 45 | 🟢 | ON RRP 餘額 | 金融 | fred | RRPONTSYD | level | 2十億美元 | 2026-07-31 |
| 46 | 🟢 | 銀行準備金餘額 | 金融 | fred | WRESBAL | level | 2,985十億美元 | 2026-07-29 |
| 47 | 🟢 | 信用OAS(IG/HY) | 金融 | fred | BAMLC0A0CM | level | 0.80% | 2026-07-30 |
