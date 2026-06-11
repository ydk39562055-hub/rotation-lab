# -*- coding: utf-8 -*-
"""
일봉 수집 (yfinance) — 증분 캐시 방식.
- config/sectors.json + config/themes.json 의 모든 티커 + 벤치마크를 모은다.
- 티커별 parquet 캐시(data/prices/{ticker}.parquet)에 저장.
- 이미 받은 날짜는 다시 요청하지 않고, 마지막 날짜 이후만 증분 수집.
- 수집 실패 티커는 건너뛰고 목록으로 반환 (전체 중단하지 않음).
"""
import os, json, time, warnings
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

warnings.simplefilter("ignore")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(HERE, "config")
PRICES = os.path.join(HERE, "data", "prices")

FIRST_FETCH_DAYS = 540  # 첫 수집 시 받아올 캘린더 일수(252일 신고가 + RS63 여유 확보)
STREAK_PATH = os.path.join(HERE, "data", "failure_streak.json")
DELIST_STREAK = 3  # 이 횟수 연속 수집 실패하면 상장폐지 의심으로 경고

# 마지막 run()에서 상장폐지 의심으로 판정된 티커 목록 (run_daily가 읽어 경고 발송)
SUSPECTS = []


def _update_streaks(bad_tickers, all_tickers_list):
    """티커별 연속 수집 실패 횟수를 기록하고, 임계치 넘은 의심 목록을 돌려준다."""
    streaks = {}
    if os.path.exists(STREAK_PATH):
        try:
            with open(STREAK_PATH, encoding="utf-8") as f:
                streaks = json.load(f)
        except Exception:
            streaks = {}
    bad = set(bad_tickers)
    for tk in all_tickers_list:
        streaks[tk] = streaks.get(tk, 0) + 1 if tk in bad else 0
    try:
        with open(STREAK_PATH, "w", encoding="utf-8") as f:
            json.dump(streaks, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return sorted(tk for tk, n in streaks.items() if n >= DELIST_STREAK)


def load_config():
    with open(os.path.join(CONFIG, "sectors.json"), encoding="utf-8") as f:
        sectors = json.load(f)
    with open(os.path.join(CONFIG, "themes.json"), encoding="utf-8") as f:
        themes = json.load(f)
    return sectors, themes


def theme_members(val):
    """테마 값에서 (구성종목 리스트, 대표ETF 또는 None) 추출. dict/리스트 형식 모두 지원."""
    if isinstance(val, dict):
        return list(val.get("tickers", [])), (val.get("etf") or None)
    return list(val), None  # 옛 리스트 형식 호환


def all_tickers(sectors, themes):
    """수집해야 할 전체 티커 집합."""
    t = set()
    t.add(sectors["benchmarks"]["us"])
    t.add(sectors["benchmarks"]["kr"])
    t.add("069500.KS")  # 시장 게이트용 KODEX200 (200일선 판정, leader-radar-kr와 동일 기준)
    for v in sectors.get("us", {}).values():
        t.add(v)
    for v in sectors.get("kr", {}).values():
        t.add(v)
    for name, val in themes.items():
        if name.startswith("_"):
            continue
        tickers, etf = theme_members(val)
        for tk in tickers:
            t.add(tk)
        if etf:
            t.add(etf)
    return sorted(t)


def _cache_path(ticker):
    safe = ticker.replace("^", "_idx_").replace("/", "_")
    return os.path.join(PRICES, f"{safe}.parquet")


def _download(ticker, start, end):
    """yfinance 단일 티커 일봉 → DataFrame[close, volume] (조정종가)."""
    df = yf.download(
        ticker, start=start, end=end, auto_adjust=True,
        progress=False, threads=False,
    )
    if df is None or df.empty:
        return None
    # 멀티인덱스 컬럼이면 평탄화
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    out = pd.DataFrame(index=pd.to_datetime(df.index))
    out["close"] = df["Close"].astype(float)
    out["volume"] = df["Volume"].astype(float) if "Volume" in df else 0.0
    out = out.dropna(subset=["close"])
    out.index.name = "date"
    return out if not out.empty else None


def fetch_ticker(ticker):
    """캐시를 보고 증분 수집. 반환: (DataFrame 또는 None, '신규/증분/캐시/실패')"""
    path = _cache_path(ticker)
    today = datetime.now().date()
    end = (today + timedelta(days=1)).strftime("%Y-%m-%d")  # yfinance end는 미포함

    cached = None
    if os.path.exists(path):
        try:
            cached = pd.read_parquet(path)
        except Exception:
            cached = None

    if cached is not None and not cached.empty:
        last = pd.to_datetime(cached.index.max()).date()
        if last >= today - timedelta(days=1):
            return cached, "캐시"  # 충분히 최신
        start = (last - timedelta(days=3)).strftime("%Y-%m-%d")  # 약간 겹쳐 받아 누락 방지
        kind = "증분"
    else:
        start = (today - timedelta(days=FIRST_FETCH_DAYS)).strftime("%Y-%m-%d")
        kind = "신규"

    try:
        fresh = _download(ticker, start, end)
    except Exception:
        fresh = None

    if fresh is None:
        if cached is not None and not cached.empty:
            return cached, "캐시(수집실패)"
        return None, "실패"

    if cached is not None and not cached.empty:
        merged = pd.concat([cached, fresh])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    else:
        merged = fresh.sort_index()

    try:
        merged.to_parquet(path)
    except Exception:
        pass
    return merged, kind


def run():
    os.makedirs(PRICES, exist_ok=True)
    sectors, themes = load_config()
    tickers = all_tickers(sectors, themes)

    prices, failures, soft_fails = {}, [], []
    print(f"[수집] 대상 티커 {len(tickers)}개")
    for i, tk in enumerate(tickers, 1):
        df, kind = fetch_ticker(tk)
        if df is None:
            failures.append(tk)
            print(f"  ({i}/{len(tickers)}) {tk:<12} 실패 — 건너뜀")
        else:
            prices[tk] = df
            if kind == "캐시(수집실패)":
                soft_fails.append(tk)  # 옛 캐시로 버텼지만 새 데이터는 못 받음
            print(f"  ({i}/{len(tickers)}) {tk:<12} {kind:<10} {len(df)}행")
        if kind in ("신규", "증분"):
            time.sleep(0.2)  # 과도한 요청 방지

    # 연속 실패 추적 → 상장폐지 의심 판정 (완전 실패 + 캐시 폴백 모두 카운트)
    global SUSPECTS
    SUSPECTS = _update_streaks(failures + soft_fails, tickers)
    if SUSPECTS:
        print(f"[경고] {DELIST_STREAK}회 연속 수집 실패(상장폐지 의심): {', '.join(SUSPECTS)}")

    print(f"[수집 완료] 성공 {len(prices)} / 실패 {len(failures)}")
    if failures:
        print(f"  실패 티커: {', '.join(failures)}")
    return prices, failures, sectors, themes


if __name__ == "__main__":
    run()
