# -*- coding: utf-8 -*-
"""
RRG(Relative Rotation Graph) 좌표 계산.
- RS-Ratio    = 자산/벤치마크 가격비율을 63일 기준 정규화(100 중심)
- RS-Momentum = RS-Ratio의 21일 변화율을 63일 기준 정규화(100 중심)
- 최근 8주(주간 샘플) 꼬리 좌표를 반환 → 4분면 산점도용
  Leading(우상) / Weakening(우하) / Lagging(좌하) / Improving(좌상)
"""
import numpy as np
import pandas as pd
from fetch import theme_members

WIN = 63   # 정규화 기준 창
MOM = 21   # 모멘텀(변화율) 기간
TAIL_WEEKS = 8    # 꼬리 길이(주) — 길수록 '주도로 가는 궤적'이 잘 보임
TOP_N = 999       # RRG에 표시할 최대 개수(큰 값=전부 표시). 줄이고 싶으면 10 등으로


def _zscore_center100(s):
    m = s.rolling(WIN).mean()
    sd = s.rolling(WIN).std()
    return 100.0 + (s - m) / sd.replace(0, np.nan)


def _quadrant(x, y):
    if x >= 100 and y >= 100:
        return "주도"
    if x >= 100 and y < 100:
        return "약화"
    if x < 100 and y < 100:
        return "부진"
    return "회복"


def rrg_coords(asset_close, bench_close):
    """단일 자산의 (rs_ratio, rs_mom) 주간 꼬리 좌표 반환."""
    df = pd.concat([asset_close.rename("a"), bench_close.rename("b")], axis=1).dropna()
    if len(df) < WIN + MOM + 5:
        return None
    rs = df["a"] / df["b"]
    rs_ratio = _zscore_center100(rs)
    mom = rs_ratio.diff(MOM)
    rs_mom = _zscore_center100(mom)
    out = pd.concat([rs_ratio.rename("x"), rs_mom.rename("y")], axis=1).dropna()
    if out.empty:
        return None
    # 최근 약 8주: 끝에서 5거래일 간격으로 표본
    tail = out.iloc[-(TAIL_WEEKS * 5):].iloc[::5].tail(TAIL_WEEKS)
    pts = [{"x": round(float(r.x), 2), "y": round(float(r.y), 2)} for r in tail.itertuples()]
    if not pts:
        return None
    last = pts[-1]
    return {"tail": pts, "quadrant": _quadrant(last["x"], last["y"])}


def _basket_close(prices, tickers):
    """테마 바스켓: 구성종목 종가를 시작=100으로 정규화해 동일가중 평균."""
    cols = []
    for t in tickers:
        df = prices.get(t)
        if df is None or df["close"].dropna().empty:
            continue
        s = df["close"].dropna()
        cols.append((s / s.iloc[0]) * 100.0)
    if not cols:
        return None
    basket = pd.concat(cols, axis=1).mean(axis=1)
    return basket.dropna()


def run(prices, comp_result, sectors, themes):
    bm = comp_result["benchmarks"]
    spy = prices.get(bm["us"])
    ks = prices.get(bm["kr"])

    sector_items, theme_items = [], []

    sector_kr_items = []

    # 종합점수 상위 N개만 RRG에 표시(난잡함 방지)
    top_us = {r["name"] for r in comp_result.get("us", [])[:TOP_N]}
    top_kr = {r["name"] for r in comp_result.get("kr", [])[:TOP_N]}
    top_th = {r["name"] for r in comp_result.get("themes", [])[:TOP_N]}

    # 섹터(미국) — vs SPY
    for name, tk in sectors.get("us", {}).items():
        if name not in top_us:
            continue
        df = prices.get(tk)
        if df is None or spy is None:
            continue
        c = rrg_coords(df["close"], spy["close"])
        if c:
            sector_items.append({"name": name, **c})

    # 섹터(한국) — vs ^KS200
    for name, tk in sectors.get("kr", {}).items():
        if name not in top_kr:
            continue
        df = prices.get(tk)
        if df is None or ks is None:
            continue
        c = rrg_coords(df["close"], ks["close"])
        if c:
            sector_kr_items.append({"name": name, **c})

    # 테마 — RRG 1장 (테마 벤치마크는 SPY 기준)
    # 대표 ETF가 있으면 그 ETF 종가로, 없으면 구성종목 동일가중 바스켓으로 그린다.
    for name, val in themes.items():
        if name.startswith("_") or name not in top_th:
            continue
        lst, etf = theme_members(val)
        if not lst or spy is None:
            continue
        if etf and prices.get(etf) is not None:
            series = prices[etf]["close"]
        else:
            members = [t for t in lst if t in prices]
            series = _basket_close(prices, members) if members else None
        if series is None:
            continue
        c = rrg_coords(series, spy["close"])
        if c:
            theme_items.append({"name": name, **c})

    return {"sectors": sector_items, "sectors_kr": sector_kr_items, "themes": theme_items}
