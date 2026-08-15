"""共用工具：設定載入、HTTP、序列轉換。"""
from __future__ import annotations

import json
import os
import time
from bisect import bisect_right
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) au-macro-guide/1.0"


def load_env() -> None:
    """本機讀 .env；GitHub Actions 直接用環境變數。"""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def get_json(url: str, params: dict | None = None, retries: int = 3) -> dict | list:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30,
                             headers={"User-Agent": UA, "Accept": "application/json"})
            r.raise_for_status()
            return r.json()
        except Exception as e:            # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"取得 JSON 失敗 {url}: {last}")


def get_text(url: str, retries: int = 3, headers: dict | None = None) -> str:
    last = None
    hdr = {"User-Agent": UA, **(headers or {})}
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30, headers=hdr)
            r.raise_for_status()
            return r.text
        except Exception as e:            # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"取得網頁失敗 {url}: {last}")


def get_impersonated(url: str, retries: int = 3, binary: bool = False):
    """給 Akamai Bot Manager 擋住的站台用（aofm.gov.au、finance.gov.au）。

    這兩個站的擋法不是回 403 而是**靜默丟棄**：TLS 握手會成功，
    然後伺服器再也不回應任何位元組直到逾時。requests / urllib / httpx
    （HTTP/1.1 與 HTTP/2 都試過）全數失敗，真實 Chrome 卻正常——
    是針對 TLS 指紋的機器人偵測，換 User-Agent 或加 header 都沒用。
    curl_cffi 會複製 Chrome 的 TLS 指紋，實測可通（2026-08-15 驗證）。

    不要為了「少一個相依套件」把這裡改回 requests——會靜靜地全部逾時。
    """
    from curl_cffi import requests as cr

    last = None
    for attempt in range(retries):
        try:
            r = cr.get(url, impersonate="chrome", timeout=45)
            r.raise_for_status()
            return r.content if binary else r.text
        except Exception as e:            # noqa: BLE001
            last = e
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"取得網頁失敗（已用 Chrome 指紋模擬）{url}: {last}")


# ---------------------------------------------------------------- 序列轉換

# qoq / qoq_diff 是澳洲特有的必要項：季頻指標（GDP、季度 CPI、WPI、Capex）
# 的頭條數字是季變動，市場與 RBA 溝通都用這個口徑。季別的日期標成該季起始月
# （2026-Q2 → 2026-04），所以往回三個月才是上一季，不能沿用月頻的 1。
MONTHS_BACK = {"yoy": 12, "mom": 1, "mom_diff": 1, "ann3m": 3, "qoq": 3, "qoq_diff": 3}
DAYS_BACK = {"yoy": 365, "mom": 30, "mom_diff": 30, "ann3m": 91, "qoq": 91, "qoq_diff": 91}
_MONTHLY_FREQ = {"M", "Q", "SA", "A", "BM"}


def _shift_months(iso: str, n: int) -> str:
    y, m, d = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}-{d:02d}"


def transform(obs: list[dict], display: str, freq: str = "M") -> list[dict]:
    """obs = [{date, value}] 由舊到新。回傳同結構的轉換後序列。

    level     原值
    yoy       年增率 %
    mom       月變動 %
    mom_diff  月變動絕對量
    qoq       季變動 %（季頻指標的頭條口徑）
    qoq_diff  季變動絕對量
    ann3m     3 個月年化 %
    ma4       4 期移動平均

    ⚠️ 基期一律以「日期」對齊，不可用「往回數 N 筆」。
    官方序列會有缺漏期別，用位置往回數會默默拿錯期別當基期，
    算出來的年增率錯了也不會有人發現。ABS 序列尤其要注意：
    季頻與月頻並存的 dataflow（如統一後的 CPI）拉下來會混在一起，
    必須先用 FREQ 維度篩過再進這個函式。
    """
    if display == "level":
        return [dict(o) for o in obs]

    vals = [o["value"] for o in obs]
    out: list[dict] = []

    if display == "ma4":
        for i, o in enumerate(obs):
            if i >= 3:
                out.append({"date": o["date"], "value": sum(vals[i - 3:i + 1]) / 4})
        return out

    by_date = {o["date"]: o["value"] for o in obs}
    dates = sorted(by_date)
    monthly = freq in _MONTHLY_FREQ

    def base_of(iso: str):
        if monthly:
            return by_date.get(_shift_months(iso, MONTHS_BACK[display]))
        # 日頻/週頻沒有整齊的日期，取「目標日之前最近的一筆」
        target = (datetime.strptime(iso[:10], "%Y-%m-%d").date()
                  - timedelta(days=DAYS_BACK[display])).isoformat()
        i = bisect_right(dates, target) - 1
        return by_date[dates[i]] if i >= 0 else None

    for o in obs:
        prev, cur = base_of(o["date"]), o["value"]
        if prev is None:
            continue
        if display in ("mom_diff", "qoq_diff"):
            v = cur - prev
        elif prev == 0:
            continue
        elif display == "ann3m":
            if prev <= 0 or cur <= 0:
                continue
            v = ((cur / prev) ** 4 - 1) * 100      # 3 個月變動年化
        else:
            v = (cur / prev - 1) * 100
        out.append({"date": o["date"], "value": v})
    return out


def days_since(iso: str) -> int:
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except ValueError:
        return 9999
    return (date.today() - d).days


# 觀測值的日期是「期別起始日」（6 月 CPI 標成 2026-06-01），
# 直接拿它算距今天數會把正常資料誤判成過期。改從期別結束日起算。
_PERIOD_DAYS = {"D": 0, "W": 6, "BW": 13, "M": 30, "Q": 91, "SA": 182, "A": 364}


def age_from_period_end(iso: str, freq: str = "M") -> int:
    return max(0, days_since(iso) - _PERIOD_DAYS.get(freq, 30))


def read_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default
    return default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
