# -*- coding: utf-8 -*-
"""
RS·breadth·거래대금흐름·랭킹·로테이션신호 계산.

RS(기간) = 자산 수익률(기간) − 벤치마크 수익률(기간)   (기간 = 21/63/126 거래일)
종합점수 = 0.5*RS126 + 0.3*RS63 + 0.2*RS21
테마 RS = 구성종목 RS의 '중앙값'(평균 아님, 한두 종목 왜곡 방지)
breadth = [52주 신고가 대비 -15% 이내] 종목 비율(%)
거래대금흐름 = (최근5일 평균 거래대금 / 최근60일 평균 거래대금) 의 중앙값
로테이션 후보 = RS126 순위 하위 50% AND RS21 순위 상위 20%

★ 2026-06-12 창 교체 (5·21·63 → 21·63·126), 백테스트 근거(backtest_windows.py):
  10년 주간 516시점·다음날 진입 비교에서 혼합 장기(126·63·21)가 미·한 섹터 모두
  옛 창(63·21·5)을 전 지평에서 이김 (미 126d: 스프레드 -0.2→+0.77%, IC +0.067).
  5일 항은 노이즈로 순위만 흔들고 예측력 없음 → 제거. 모멘텀은 3~12개월 창에서만 실재.
"""
import os, json
from datetime import datetime
import numpy as np
import pandas as pd
from fetch import theme_members

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(HERE, "data", "history")
PERIODS = {"rs21": 21, "rs63": 63, "rs126": 126}
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
    vals = [rs.get("rs126"), rs.get("rs63"), rs.get("rs21")]
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
        b = _breadth_one(df)
        b = 0.0 if b is None or (isinstance(b, float) and np.isnan(b)) else b
        rows.append({
            "name": name, "tickers": [tk], "n": 1,
            "rs21": rs["rs21"], "rs63": rs["rs63"], "rs126": rs["rs126"],
            "breadth": b * 100.0,
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
        rs21 = _nanmedian([ticker_rs(prices, t, bench_rets)["rs21"] for t in members])
        rs63 = _nanmedian([ticker_rs(prices, t, bench_rets)["rs63"] for t in members])
        rs126 = _nanmedian([ticker_rs(prices, t, bench_rets)["rs126"] for t in members])
        # breadth = 0/1 지표라 '비율'이 의미 — 유효 종목들의 평균(%)을 그대로 쓴다
        breadth_vals = [b for b in (_breadth_one(prices[t]) for t in members)
                        if b is not None and not np.isnan(b)]
        breadth = 100.0 * float(np.mean(breadth_vals)) if breadth_vals else np.nan
        flow = _nanmedian([_flow_one(prices[t]) for t in members])
        comp = _composite({"rs21": rs21, "rs63": rs63, "rs126": rs126})
        rows.append({
            "name": name, "tickers": members, "n": len(members), "etf": etf,
            "rs21": rs21, "rs63": rs63, "rs126": rs126,
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
    rs126_rank = _rank_by(rows, "rs126")
    rs21_rank = _rank_by(rows, "rs21")
    n = len(rows)
    # 표본이 5개 미만이면 '하위 50% + 상위 20%' 조합이 무의미 → 로테이션 판정 생략
    rotation_enabled = n >= 5
    top_k = max(1, round(n * 0.2))
    for i, r in enumerate(rows):
        r["rank"] = comp_rank[i]
        # 로테이션 후보: RS126(장기) 하위 50% AND RS21(단기) 상위 20%
        bottom_half_l = rs126_rank[i] > n * 0.5
        top20_s = rs21_rank[i] <= top_k
        r["rotation"] = bool(rotation_enabled and bottom_half_l and top20_s)
    rows.sort(key=lambda r: r["rank"])
    return rows


# ── 판정(verdict) 엔진 ───────────────────────────────────────────────
VERDICTS = {
    "lead":    {"emoji": "🟢", "name": "주도지속",   "action": "1순위 — 이 테마에서 종목 탐색"},
    "pull":    {"emoji": "🟡", "name": "건강한눌림", "action": "진입 대기 — RS5 양전환 시 1순위 승격"},
    "break":   {"emoji": "🟠", "name": "꺾임의심",   "action": "보유분 경계 — 신규 금지"},
    "recover": {"emoji": "🔵", "name": "회복진행",   "action": "관찰 리스트 — 3일 연속 유지 시 후보"},
    "blip":    {"emoji": "⚪", "name": "반짝반등",   "action": "무시 (가짜 반등 추정)"},
    "laggard": {"emoji": "⚫", "name": "소외",       "action": "무시"},
}


def classify(row, allow_breadth_corr=True):
    """RS126(장기)/RS63(중기)/RS21(단기) 부호로 기본 분류 후 breadth·거래대금·순위모멘텀 보정."""
    rs21, rs63, rs126 = row.get("rs21"), row.get("rs63"), row.get("rs126")
    if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in (rs21, rs63, rs126)):
        return {"key": None, "emoji": "—", "name": "판정불가", "action": "데이터 부족", "flags": []}

    # 1. 기본 트리 (장기 추세가 기준, 단기·중기로 국면 구분)
    if rs126 >= 0:
        key = "lead" if rs21 >= 0 else ("pull" if rs63 >= 0 else "break")
    else:
        if rs21 >= 0:
            key = "recover" if rs63 >= 0 else "blip"
        else:
            key = "laggard"

    flags = []
    # 2a. breadth 보정 (멤버 여러 개인 테마만)
    breadth = row.get("breadth")
    if allow_breadth_corr and breadth is not None and not np.isnan(breadth) and breadth < 25:
        flags.append("⚠️쏠림")
        if key == "lead":
            key = "pull"
        elif key == "pull":
            key = "break"
    # 2b. 거래대금 보정
    flow = row.get("flow")
    if flow is not None and not np.isnan(flow):
        if key == "blip" and flow >= 1.2:
            key = "recover"
            flags.append("🔄")
        elif key == "recover" and flow <= 0.9:
            key = "blip"
    # 2c. 순위 모멘텀
    d5 = row.get("delta5")
    if d5 is not None and d5 >= 3:
        flags.append("↗급부상")

    v = VERDICTS[key]
    return {"key": key, "emoji": v["emoji"], "name": v["name"], "action": v["action"], "flags": flags}


def _below_ma200(prices, ticker):
    """현재 종가가 200일 이동평균 아래면 True(약세 게이트). 데이터 부족 시 None."""
    df = prices.get(ticker)
    if df is None:
        return None
    s = df["close"].dropna()
    if len(s) < 200:
        return None
    return bool(s.iloc[-1] < s.iloc[-200:].mean())


def _conclusion(themes_rows, gate_us, prev_vd):
    """대시보드 최상단 '오늘의 결론' 3줄 생성."""
    def names(keys):
        return [r["name"] for r in themes_rows if r["verdict"]["key"] in keys]
    greens, yellows, blues = names(["lead"]), names(["pull"]), names(["recover"])

    # 1줄: 게이트 + 주도
    if gate_us:
        line1 = "⛔ 시장 약세(SPY 200일선 아래) — 신규 진입 전체 보류"
    elif greens:
        line1 = "🟢 주도 지속: " + ", ".join(greens)
    else:
        line1 = "주도 테마 휴식 중 — 신규 진입 자리 없음"

    # 2줄: 눌림 대기 + 회복 관찰
    parts = []
    if yellows:
        parts.append("🟡 눌림 대기: " + ", ".join(yellows))
    if blues:
        parts.append("🔵 회복 관찰: " + ", ".join(blues))
    line2 = " · ".join(parts) if parts else "눌림·회복 후보 없음"

    # 3줄: 전일 대비 판정 변화 (첫날은 생략)
    lines = [line1, line2]
    if prev_vd:
        changes = []
        for r in themes_rows:
            old = prev_vd.get(r["name"])
            new = r["verdict"]["emoji"]
            if old and new and old != new:
                changes.append(f"{r['name']} {old}→{new}")
        if changes:
            lines.append("변화: " + ", ".join(changes))
    return lines


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

    # 판정 부여 (테마=breadth 보정 적용, 섹터=ETF 1개라 미적용)
    for r in themes_rows:
        r["verdict"] = classify(r, allow_breadth_corr=(r.get("n", 1) > 1))
    for r in us_rows + kr_rows:
        r["verdict"] = classify(r, allow_breadth_corr=False)

    # 시장 게이트
    gate = {"us": bool(_below_ma200(prices, "SPY")),
            "kr": bool(_below_ma200(prices, "069500.KS"))}

    # 전일 판정(변화 비교용) → 결론 생성
    dates = sorted(d for d in hist.keys() if d < today)
    prev_vd = hist.get(dates[-1], {}).get("vd_theme") if dates else None
    conclusion = _conclusion(themes_rows, gate["us"], prev_vd)

    # 오늘 순위 + 판정 저장(다음 실행 비교용)
    hist[today] = {
        "theme": [r["name"] for r in themes_rows],
        "us": [r["name"] for r in us_rows],
        "kr": [r["name"] for r in kr_rows],
        "vd_theme": {r["name"]: r["verdict"]["emoji"] for r in themes_rows},
    }
    _save_history(hist)

    # 퍼널 연동: 🟢=go, 🟡+🔵=watch 테마의 구성종목 → output/strong_themes.json
    _write_strong_themes(today, themes_rows)

    return {
        "date": today,
        "themes": themes_rows,
        "us": us_rows,
        "kr": kr_rows,
        "benchmarks": sectors["benchmarks"],
        "gate": gate,
        "conclusion": conclusion,
    }


def _write_strong_themes(today, themes_rows):
    go, watch = [], []
    for r in themes_rows:
        k = r["verdict"]["key"]
        if k == "lead":
            go.extend(r.get("tickers", []))
        elif k in ("pull", "recover"):
            watch.extend(r.get("tickers", []))
    payload = {"date": today,
               "go": sorted(set(go)),
               "watch": sorted(set(watch))}
    # repo 루트에 저장 → publish()가 GitHub Pages로 푸시 → leader-radar가 URL로 읽음
    with open(os.path.join(HERE, "strong_themes.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    from fetch import run as fetch_run
    prices, failures, sectors, themes = fetch_run()
    res = run(prices, sectors, themes)
    for r in res["themes"]:
        print(r["rank"], r["name"], round(r["composite"], 2) if not np.isnan(r["composite"]) else "—")
