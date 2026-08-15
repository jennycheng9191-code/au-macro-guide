"""規則式判讀引擎 —— 自動生成每張卡的「現況判讀」。

只寫規則算得出來的話。跨指標推理、地緣事件干擾這類需要判斷的評論
一律留白，不自動編造——寧可沒有，不可亂寫。

輸出風格對齊原手冊：一句話、繁體中文、40 字內。
"""
from __future__ import annotations


# ---------------------------------------------------------------- 指標專屬規則

def sahm_rule(res: dict, **_) -> str | None:
    """失業率：3 個月均值 − 過去 12 個月低點，0.5pp 為衰退訊號門檻。"""
    vals = [h["value"] for h in res.get("history", [])]
    if len(vals) < 15:
        return None
    ma3 = sum(vals[-3:]) / 3
    low12 = min(sum(vals[i - 2:i + 1]) / 3 for i in range(len(vals) - 12, len(vals)))
    gap = ma3 - low12
    if gap >= 0.5:
        return f"Sahm Rule 計數 {gap:.2f}pp，已觸發 0.5pp 衰退訊號門檻"
    return f"Sahm Rule 計數 {gap:.2f}pp，距 0.5pp 觸發門檻尚有 {0.5 - gap:.2f}pp"


def pmi_50_line(res: dict, **_) -> str | None:
    v = res.get("value")
    if v is None:
        return None
    side = "高於" if v >= 50 else "低於"
    return f"{side} 50 榮枯線"


def pmi_45_recession(res: dict, **_) -> str | None:
    v = res.get("value")
    if v is None:
        return None
    return "已跌破對應整體衰退的 45 門檻" if v < 45 else "未跌破對應整體衰退的 45 門檻"


def deanchor_2_5(res: dict, **_) -> str | None:
    v = res.get("value")
    if v is None:
        return None
    return ("站上 2.5% 去錨警戒線" if v >= 2.5
            else f"距 2.5% 去錨警戒線尚有 {2.5 - v:.2f}pp")


def core_vs_target(res: dict, **_) -> str | None:
    """核心 CPI 需在 2.4% 以下才與 2% PCE 目標相容（CPI-PCE 楔差）。"""
    a = (res.get("also") or {}).get("ann3m")
    if a is None:
        return None
    return (f"3 個月年化 {a:.1f}%，"
            + ("已進入與 2% 目標相容區（2.4% 以下）" if a <= 2.4 else "仍高於相容區上緣 2.4%"))


def wage_compat_3_0_3_5(res: dict, **_) -> str | None:
    v = res.get("value")
    if v is None:
        return None
    v = round(v, 1)        # 比較與顯示用同一個值，避免「顯示 3.5 卻說高於 3.5」
    if v > 3.5:
        return f"年增 {v:.1f}%，高於與 2% 通膨相容區（3.0–3.5%）"
    if v < 3.0:
        return f"年增 {v:.1f}%，低於相容區下緣 3.0%"
    return f"年增 {v:.1f}%，落在與 2% 通膨相容區內"


def eci_compat_3_5(res: dict, **_) -> str | None:
    v = res.get("value")
    if v is None:
        return None
    v = round(v, 1)
    return (f"年增 {v:.1f}%，{'高於' if v > 3.5 else '未超過'}與 2% 相容的 3.5% 參考線")


def v_u_ratio(res: dict, **_) -> str | None:
    ex = res.get("extras") or {}
    jobs, unemp = res.get("value"), ex.get("失業人數")
    if not jobs or not unemp:
        return None
    r = jobs / unemp
    return (f"V/U 比 {r:.2f}，"
            + ("已回落至 1.0 以下，勞動市場鬆弛確認" if r < 1.0 else "尚未跌破 1.0 鬆弛門檻"))


def breakeven_100_150(res: dict, **_) -> str | None:
    v = res.get("value")
    if v is None:
        return None
    if v < 100:
        return f"月增 {v:.0f}千人，低於 10–15 萬盈虧平衡區間"
    if v > 150:
        return f"月增 {v:.0f}千人，高於 10–15 萬盈虧平衡區間"
    return f"月增 {v:.0f}千人，落在 10–15 萬盈虧平衡區間內"


def claims_range_break(res: dict, **_) -> str | None:
    vals = [h["value"] for h in res.get("history", [])]
    if len(vals) < 12:
        return None
    v, prior = vals[-1], vals[-13:-1]
    if v > max(prior):
        return f"突破過去 12 週區間上緣（前高 {max(prior):,.0f}）"
    if v < min(prior):
        return f"跌破過去 12 週區間下緣（前低 {min(prior):,.0f}）"
    return "仍在過去 12 週的區間內波動"


def tbac_15_20(res: dict, **_) -> str | None:
    v = res.get("value")
    if v is None:
        return None
    if v > 20:
        return f"占比 {v:.1f}%，超出 TBAC 建議的 15–20% 區間"
    if v < 15:
        return f"占比 {v:.1f}%，低於 TBAC 建議區間下緣"
    return f"占比 {v:.1f}%，落在 TBAC 建議的 15–20% 區間內"


def nowcast_prior_error(res: dict, **_) -> str | None:
    """上一個目標月的預測誤差——判斷這份 nowcast 現在準不準的唯一依據。"""
    p = res.get("prior")
    if not p:
        return None
    err = p["nowcast"] - p["actual"]
    good = "誤差在 0.1pp 內" if abs(err) <= 0.1 else f"高估 {err:.2f}pp" if err > 0 else f"低估 {-err:.2f}pp"
    return f"上期（{p['month']}）預估 {p['nowcast']:+.2f}%、實際 {p['actual']:+.2f}%，{good}"


def nfci_zero_line(res: dict, **_) -> str | None:
    v = res.get("value")
    if v is None:
        return None
    return (f"{'低於' if v < 0 else '高於'} 0（歷史均值），"
            + ("金融條件偏寬鬆" if v < 0 else "金融條件偏緊縮"))


def auction_size_change(res: dict, **_) -> str | None:
    """跟同年期上一場標售比規模——QRA 若真的調整發債量，第一手會反映在這裡。"""
    diff = (res.get("extras") or {}).get("規模變動(十億美元)")
    if diff is None:
        return None
    direction = "增額" if diff > 0 else "減額"
    return f"標售規模較上次{direction} {abs(diff):.1f}十億美元"


def sofr_iorb_persistent(res: dict, **_) -> str | None:
    vals = [h["value"] for h in res.get("history", [])]
    v = res.get("value")
    if v is None:
        return None
    if len(vals) >= 5:
        above = sum(1 for x in vals[-5:] if x > 0)
        if above >= 4:
            return f"利差 {v:.1f}bp，近 5 個交易日有 {above} 日 SOFR 升穿 IORB"
    return f"利差 {v:.1f}bp，{'SOFR 高於' if v > 0 else 'SOFR 低於'} IORB"


RULES = {f.__name__: f for f in [
    sahm_rule, pmi_50_line, pmi_45_recession, deanchor_2_5, core_vs_target,
    wage_compat_3_0_3_5, eci_compat_3_5, v_u_ratio, breakeven_100_150,
    claims_range_break, tbac_15_20, nfci_zero_line, sofr_iorb_persistent,
    nowcast_prior_error, auction_size_change,
]}


# ---------------------------------------------------------------- 通用規則

def generic(res: dict) -> str | None:
    """所有卡都適用：連續同向期數 / 相對 24 期的位置。"""
    vals = [h["value"] for h in res.get("history", [])]
    if len(vals) < 6:
        return None

    diffs = [b - a for a, b in zip(vals, vals[1:])]
    streak, sign = 0, (1 if diffs[-1] > 0 else -1 if diffs[-1] < 0 else 0)
    if sign:
        for d in reversed(diffs):
            if (d > 0) == (sign > 0) and d != 0:
                streak += 1
            else:
                break

    bits = []
    if streak >= 3:
        bits.append(f"連續 {streak} 期{'走升' if sign > 0 else '走降'}")

    # 百分位是事實陳述（不是判斷），一律給——否則多數卡片會整句留白。
    # 觸及區間端點時改用更有訊息量的「創新高／新低」。
    v = vals[-1]
    if v >= max(vals):
        bits.append(f"創近 {len(vals)} 期新高")
    elif v <= min(vals):
        bits.append(f"創近 {len(vals)} 期新低")
    else:
        rank = sum(1 for x in vals if x <= v) / len(vals) * 100
        bits.append(f"位於近 {len(vals)} 期的第 {rank:.0f} 百分位")

    return "、".join(bits) if bits else None


def build_note(res: dict, m: dict) -> str:
    """組合出一句判讀。規則算不出來就留白，不編造。"""
    parts: list[str] = []
    for name in m.get("rules", []):
        fn = RULES.get(name)
        if not fn:
            continue
        try:
            if (s := fn(res, m=m)):
                parts.append(s)
        except Exception:                      # noqa: BLE001
            continue
    try:
        if (g := generic(res)):
            parts.append(g)
    except Exception:                          # noqa: BLE001
        pass
    return "；".join(parts)
