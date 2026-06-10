# -*- coding: utf-8 -*-
"""
RS·breadth·거래대금흐름·랭킹·로테이션신호 계산.

RS(기간) = 자산 수익률(기간) − 벤치마크 수익률(기간)   (기간 = 5/21/63 거래일)
종합점수 = 0.5*RS63 + 0.3*RS21 + 0.2*RS5
테마 RS = 구성종목 RS의 '중앙값'(평균 아님, 한두 종목 왜곡 방지)
breadth = [52주 신고가 대비 -15% 이내] 종목 비율(%)
거래대금흐름 = (최근5일 평균 거래대금 / 최근60일 평균 거래대금) 의 중앙값
로테이션 후보 = RS63 순위 하위 50% AND RS5 순위 상위 20%
"""
import os, json
from datetime import datetime
import numpy as np
import pandas as pd
from fetch import theme_members

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(HERE, "data", "history")
PERIODS = {"rs5": 5, "rs21": 21, "rs63": 63}
W63, W21, W5, W60, W252 = 63, 21, 5, 60, 252


def _ret(series, n):
    """최근 n 거래일 수익률."""
    s = series.dropna()
    if len(s) < n + 1:
        return np.nan
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1.0)


def bench_key(ticker):
    return "kr" if ticker.endswith((".KS", ".KQ")) else "us"


def _bench_rets(prices, benchmarks):
    out = {}
    for mkt, btk in benchmarks.items():
        df = prices.get(btk)
        out[mkt] = {p: (_ret(df["close"], n) if df is not None else np.nan)
                    for p, n in PERIODS.items()}
    return out


def ticker_rs(prices, ticker, bench_rets):
    """단일 티커의 RS5/21/63 (자기 시장 벤치마크 기준)."""
    df = prices.get(ticker)
    if df is None:
        return None
    mkt = bench_key(ticker)
    br = bench_rets[mkt]
    rs = {}
    for p, n in PERIODS.items():
        r = _ret(df["close"], n)
        rs[p] = np.nan if (np.isnan(r) or np.isnan(br[p])) else (r - br[p]) * 100.0
    return rs


def _breadth_one(df):
    """52주 신고가 대비 -15% 이내면 1, 아니면 0."""
    s = df["close"].dropna()
    if len(s) < 20:
        return np.nan
    hi = s.iloc[-min(W252, len(s)):].max()
    return 1.0 if s.iloc[-1] >= 0.85 * hi else 0.0


def _flow_one(df):
    """거래대금흐름 = avg5(거래대금) / avg60(거래대금)."""
    s = df.dropna()
    if len(s) < W5:
        return np.nan
    dv = (s["close"] * s["volume"]).dropna()
    if len(dv) < W5 or dv.iloc[-W5:].mean() == 0:
        return np.nan
    a5 = dv.iloc[-W5:].mean()
    a60 = dv.iloc[-min(W60, len(dv)):].mean()
    return float(a5 / a60) if a60 else np.nan


def _composite(rs):
    vals = [rs.get("rs63"), rs.get("rs21"), rs.get("rs5")]
    if any(v is None or np.isnan(v) for v in vals):
        return np.nan
    return 0.5 * vals[0] + 0.3 * vals[1] + 0.2 * vals[2]


def _nanmedian(arr):
    arr = [x for x in arr if x is not None and not np.isnan(x)]
    return float(np.median(arr)) if arr else np.nan


def compute_sectors(prices, mapping, bench_rets):
    rows = []
    for name, tk in mapping.items():
        rs = ticker_rs(prices, tk, bench_rets)
        df = prices.get(tk)
        if rs is None or df is None:
            continue
        rows.append({
            "name": name, "tickers": [tk], "n": 1,
            "rs5": rs["rs5"], "rs21": rs["rs21"], "rs63": rs["rs63"],
            "breadth": (_breadth_one(df) or 0) * 100.0,
            "flow": _flow_one(df),
            "composite": _composite(rs),
        })
    return rows


def compute_themes(prices, themes, bench_rets):
    rows = []
    for name, val in themes.items():
        if name.startswith("_"):
            continue
        lst, etf = theme_members(val)
        if not lst:
            continue
        members = [t for t in lst if t in prices]
        if not members:
            continue
        rs5 = _nanmedian([ticker_rs(prices, t, bench_rets)["rs5"] for t in members])
        rs21 = _nanmedian([ticker_rs(prices, t, bench_rets)["rs21"] for t in members])
        rs63 = _nanmedian([ticker_rs(prices, t, bench_rets)["rs63"] for t in members])
        breadth_vals = [_breadth_one(prices[t]) for t in members]
        breadth = _nanmedian(breadth_vals)
        breadth = np.nan if np.isnan(breadth) else (
            100.0 * np.mean([b for b in breadth_vals if b is not None and not np.isnan(b)]))
        flow = _nanmedian([_flow_one(prices[t]) for t in members])
        comp = _composite({"rs5": rs5, "rs21": rs21, "rs63": rs63})
        rows.append({
            "name": name, "tickers": members, "n": len(members), "etf": etf,
            "rs5": rs5, "rs21": rs21, "rs63": rs63,
            "breadth": breadth, "flow": flow, "composite": comp,
        })
    return rows


def _rank_by(rows, key, reverse=True):
    """key 기준 순위(1=최상). NaN은 맨 뒤."""
    order = sorted(range(len(rows)),
                   key=lambda i: (np.isnan(rows[i].get(key, np.nan)),
                                  -rows[i].get(key, np.nan) if reverse else rows[i].get(key, np.nan)))
    rank = {}
    for pos, i in enumerate(order, 1):
        rank[i] = pos
    return rank


def _apply_ranks_and_signals(rows):
    """종합점수로 순위 매기고, 로테이션 후보 태그."""
    if not rows:
        return rows
    comp_rank = _rank_by(rows, "composite")
    rs63_rank = _rank_by(rows, "rs63")
    rs5_rank = _rank_by(rows, "rs5")
    n = len(rows)
    for i, r in enumerate(rows):
        r["rank"] = comp_rank[i]
        # 로테이션 후보: RS63 하위 50% AND RS5 상위 20%
        bottom_half_63 = rs63_rank[i] > n * 0.5
        top20_5 = rs5_rank[i] <= max(1, n * 0.2)
        r["rotation"] = bool(bottom_half_63 and top20_5)
    rows.sort(key=lambda r: r["rank"])
    return rows


def _load_history():
    path = os.path.join(HIST, "rankings.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_history(hist):
    os.makedirs(HIST, exist_ok=True)
    with open(os.path.join(HIST, "rankings.json"), "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)


def _deltas(rows, scope, hist, today):
    """전일 대비 / 5거래일(=5실행) 전 대비 순위 변화. (양수 = 상승)"""
    dates = sorted(d for d in hist.keys() if d < today)
    prev = hist.get(dates[-1], {}).get(scope) if dates else None
    prev5 = hist.get(dates[-5], {}).get(scope) if len(dates) >= 5 else None

    def rank_in(order, name):
        return (order.index(name) + 1) if (order and name in order) else None

    for r in rows:
        pr = rank_in(prev, r["name"]) if prev else None
        p5 = rank_in(prev5, r["name"]) if prev5 else None
        r["delta1"] = (pr - r["rank"]) if pr is not None else None
        r["delta5"] = (p5 - r["rank"]) if p5 is not None else None
    return rows


def run(prices, sectors, themes):
    today = datetime.now().strftime("%Y-%m-%d")
    bench_rets = _bench_rets(prices, sectors["benchmarks"])

    themes_rows = _apply_ranks_and_signals(compute_themes(prices, themes, bench_rets))
    us_rows = _apply_ranks_and_signals(compute_sectors(prices, sectors.get("us", {}), bench_rets))
    kr_rows = _apply_ranks_and_signals(compute_sectors(prices, sectors.get("kr", {}), bench_rets))

    hist = _load_history()
    _deltas(themes_rows, "theme", hist, today)
    _deltas(us_rows, "us", hist, today)
    _deltas(kr_rows, "kr", hist, today)

    # 오늘 순위 저장(다음 실행의 ▲▼ 비교용)
    hist[today] = {
        "theme": [r["name"] for r in themes_rows],
        "us": [r["name"] for r in us_rows],
        "kr": [r["name"] for r in kr_rows],
    }
    _save_history(hist)

    return {
        "date": today,
        "themes": themes_rows,
        "us": us_rows,
        "kr": kr_rows,
        "benchmarks": sectors["benchmarks"],
    }


if __name__ == "__main__":
    from fetch import run as fetch_run
    prices, failures, sectors, themes = fetch_run()
    res = run(prices, sectors, themes)
    for r in res["themes"]:
        print(r["rank"], r["name"], round(r["composite"], 2) if not np.isnan(r["composite"]) else "—")
