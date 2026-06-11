# -*- coding: utf-8 -*-
"""
로테이션 랩 판정엔진 백테스트 — "🟢주도지속(1등급) 판정이 뜨면 이후 실제로 시장을 이겼나?"

설계 (2026-06-11, leader-radar 백테스트 보정 교훈 반영):
- 매주(5거래일 간격) 스냅샷: 그 시점까지의 데이터만으로 RS·종합점수·판정(classify) 재계산
- ★진입 = 스냅샷 '다음' 거래일 (선견편향 제거)
- 성과 = 이후 +5/+21/+63 거래일의 '벤치마크 대비 초과수익' (자기 시장 벤치 기준)
- 승 = 초과수익 > 0
- 판정 로직은 운영 코드(src/compute.py classify)를 그대로 import — 재구현 금지

정직한 한계 (결과 해석 시 필수):
1. 테마 구성은 '지금' 리스트 → 사후선택 편향 (지금 뜨거운 테마를 과거에 적용). 테마 결과는 부풀려짐.
   미국 11섹터·한국 10섹터 ETF는 구성 고정이라 깨끗함 → 섹터 결과가 진짜 시험지.
2. 주간 스냅샷 + 21/63일 측정 = 표본이 서로 겹침(독립 아님). n은 보이는 것보다 실질적으로 작음.
3. 신생 종목은 데이터 쌓인 뒤부터 테마에 합류 (그 전엔 제외).
"""
import os, sys, io, json
import numpy as np
import pandas as pd

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
from fetch import load_config, theme_members, all_tickers          # noqa: E402
from compute import classify, PERIODS, VERDICTS                     # noqa: E402

START = "2015-01-01"
WARMUP = 300            # 최소 보유 데이터 (252일 신고가 + RS63 여유)
STEP = 5                # 스냅샷 간격 (5거래일 = 주간)
HORIZONS = (21, 63, 126)  # 성과 측정 구간 (거래일) — 새 창은 1~6개월 보유가 의미 구간
CACHE = os.path.join(HERE, "data", "backtest_prices.pkl")


# ── 데이터 ───────────────────────────────────────────────────────────
def download_all():
    sectors, themes = load_config()
    tickers = all_tickers(sectors, themes)
    if os.path.exists(CACHE):
        try:
            store = pd.read_pickle(CACHE)
            if set(tickers) <= set(store["close"].columns):
                print(f"[캐시] {CACHE} 재사용")
                return store["close"], store["volume"], sectors, themes
        except Exception:
            pass
    import yfinance as yf
    print(f"[다운로드] {len(tickers)}개 티커, {START} 이후 (백테스트 전용 캐시)")
    data = yf.download(tickers, start=START, auto_adjust=True, progress=False, threads=False)
    close, volume = data["Close"], data["Volume"]
    pd.to_pickle({"close": close, "volume": volume}, CACHE)
    return close, volume, sectors, themes


# ── 시점 t 기준 계산 (t 이후 데이터 절대 사용 금지) ────────────────────
def _ret_at(s, n):
    """시리즈 s(이미 t까지 잘린 상태)의 최근 n거래일 수익률."""
    s = s.dropna()
    if len(s) < n + 1:
        return np.nan
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1.0)


def _bench_key(tk):
    return "kr" if tk.endswith((".KS", ".KQ")) else "us"


def _rs_at(close_t, tk, bench_rets):
    s = close_t.get(tk)
    if s is None:
        return None
    br = bench_rets[_bench_key(tk)]
    rs = {}
    for p, n in PERIODS.items():
        r = _ret_at(s, n)
        rs[p] = np.nan if (np.isnan(r) or np.isnan(br[p])) else (r - br[p]) * 100.0
    return rs


def _breadth_at(s):
    s = s.dropna()
    if len(s) < 64:
        return np.nan
    hi = s.iloc[-min(252, len(s)):].max()
    return 1.0 if s.iloc[-1] >= 0.85 * hi else 0.0


def _flow_at(close_s, vol_s):
    dv = (close_s * vol_s).dropna()
    if len(dv) < 5:
        return np.nan
    a5 = dv.iloc[-5:].mean()
    a60 = dv.iloc[-min(60, len(dv)):].mean()
    return float(a5 / a60) if a60 else np.nan


def _composite(rs):
    v = [rs.get("rs126"), rs.get("rs63"), rs.get("rs21")]
    if any(x is None or np.isnan(x) for x in v):
        return np.nan
    return 0.5 * v[0] + 0.3 * v[1] + 0.2 * v[2]


# ── 미래 성과 (진입 = t 다음 거래일) ──────────────────────────────────
def _fwd_excess(close, tk, bench_tk, t, horizon):
    """t 다음 거래일 종가 진입 → horizon 거래일 뒤 종가. 벤치 대비 초과수익(%p)."""
    s = close[tk].dropna()
    pos = s.index.searchsorted(t, side="right")   # t 이후 첫 거래일
    if pos + horizon >= len(s):
        return None
    d0, d1 = s.index[pos], s.index[pos + horizon]
    a = float(s.iloc[pos + horizon] / s.iloc[pos] - 1.0)
    b = close[bench_tk].dropna()
    b0, b1 = b.asof(d0), b.asof(d1)
    if pd.isna(b0) or pd.isna(b1) or b0 == 0:
        return None
    return (a - float(b1 / b0 - 1.0)) * 100.0


# ── 메인 루프 ────────────────────────────────────────────────────────
def run():
    close, volume, sectors, themes = download_all()
    bench = sectors["benchmarks"]                      # {"us": "SPY", "kr": "^KS200"}
    spy = close[bench["us"]].dropna()
    snaps = spy.index[WARMUP::STEP]
    print(f"[스냅샷] {len(snaps)}개 (주간, {snaps[0].date()} ~ {snaps[-1].date()})")

    theme_defs = {n: theme_members(v) for n, v in themes.items() if not n.startswith("_")}
    records = []   # (universe, verdict_key, rank, horizon, excess)

    for si, t in enumerate(snaps):
        close_t = {tk: close[tk].loc[:t] for tk in close.columns}
        bench_rets = {}
        for m, btk in bench.items():
            if btk in close_t:
                bench_rets[m] = {p: _ret_at(close_t[btk], n) for p, n in PERIODS.items()}

        # 1) 섹터 (구성 고정 → 깨끗한 시험지)
        for scope, mapping in (("us섹터", sectors.get("us", {})), ("kr섹터", sectors.get("kr", {}))):
            rows = []
            for name, tk in mapping.items():
                if tk not in close_t:
                    continue
                rs = _rs_at(close_t, tk, bench_rets)
                if rs is None:
                    continue
                comp = _composite(rs)
                if np.isnan(comp):
                    continue
                rows.append({"name": name, "tk": tk, **rs, "composite": comp,
                             "breadth": np.nan,
                             "flow": _flow_at(close_t[tk], volume[tk].loc[:t])})
            rows.sort(key=lambda r: -r["composite"])
            for rank, r in enumerate(rows, 1):
                vd = classify(r, allow_breadth_corr=False)
                btk = bench[_bench_key(r["tk"])]
                for h in HORIZONS:
                    ex = _fwd_excess(close, r["tk"], btk, t, h)
                    if ex is not None:
                        records.append((scope, vd["key"], rank, h, ex))

        # 2) 테마 (사후선택 편향 → 참고용)
        rows = []
        for name, (members, etf) in theme_defs.items():
            ms = [m for m in members if m in close_t and len(close_t[m].dropna()) >= 64]
            if not ms:
                continue
            rs_list = [_rs_at(close_t, m, bench_rets) for m in ms]
            rs_list = [x for x in rs_list if x is not None]
            if not rs_list:
                continue
            def med(p):
                vals = [x[p] for x in rs_list if not np.isnan(x[p])]
                return float(np.median(vals)) if vals else np.nan
            rs = {p: med(p) for p in PERIODS}
            comp = _composite(rs)
            if np.isnan(comp):
                continue
            bvals = [b for b in (_breadth_at(close_t[m]) for m in ms) if not np.isnan(b)]
            breadth = 100.0 * float(np.mean(bvals)) if bvals else np.nan
            fvals = [f for f in (_flow_at(close_t[m], volume[m].loc[:t]) for m in ms)
                     if not np.isnan(f)]
            flow = float(np.median(fvals)) if fvals else np.nan
            rows.append({"name": name, "members": ms, **rs, "composite": comp,
                         "breadth": breadth, "flow": flow})
        rows.sort(key=lambda r: -r["composite"])
        for rank, r in enumerate(rows, 1):
            vd = classify(r, allow_breadth_corr=(len(r["members"]) > 1))
            for h in HORIZONS:
                exs = []
                for m in r["members"]:
                    ex = _fwd_excess(close, m, bench[_bench_key(m)], t, h)
                    if ex is not None:
                        exs.append(ex)
                if exs:
                    records.append(("테마", vd["key"], rank, h, float(np.mean(exs))))

        if (si + 1) % 50 == 0:
            print(f"  진행 {si+1}/{len(snaps)}", flush=True)

    # ── 집계 ──
    df = pd.DataFrame(records, columns=["universe", "verdict", "rank", "h", "excess"])
    print(f"\n[표본] 총 {len(df):,}건 (판정×지평 단위)")
    order = ["lead", "pull", "break", "recover", "blip", "laggard"]
    name_of = {k: f"{VERDICTS[k]['emoji']}{VERDICTS[k]['name']}" for k in order}

    for uni in ["us섹터", "kr섹터", "테마"]:
        d = df[df.universe == uni]
        if d.empty:
            continue
        print(f"\n{'='*72}\n {uni}  (스냅샷 주간 · 진입=다음 거래일 · 성과=자기 벤치 대비 초과수익)\n{'='*72}")
        print(f"  {'판정':<14}{'지평':>6}{'n':>7}{'승률':>8}{'평균초과':>10}{'중앙값':>9}")
        for k in order:
            for h in HORIZONS:
                x = d[(d.verdict == k) & (d.h == h)]["excess"]
                if len(x) < 10:
                    continue
                win = (x > 0).mean() * 100
                print(f"  {name_of[k]:<14}{h:>5}d{len(x):>7}{win:>7.0f}%{x.mean():>+9.2f}%{x.median():>+8.2f}%")
            print()
        # 베이스라인 + 종합 1등
        for h in HORIZONS:
            x = d[d.h == h]["excess"]
            r1 = d[(d["rank"] == 1) & (d.h == h)]["excess"]
            print(f"  [기준선] 전체평균 {h:>3}d: n={len(x):>5} 승률 {(x>0).mean()*100:>3.0f}% 평균 {x.mean():+.2f}%"
                  f"   |   [종합1등] n={len(r1):>4} 승률 {(r1>0).mean()*100:>3.0f}% 평균 {r1.mean():+.2f}%")

    print("\n[한계 고지] 테마=사후선택 편향(지금 리스트를 과거에 적용) → 섹터 결과가 진짜 시험지.")
    print("           주간 스냅샷·중첩 측정구간 → n은 실질보다 커 보임. 승률 1~2%p 차이는 노이즈.")


if __name__ == "__main__":
    run()
