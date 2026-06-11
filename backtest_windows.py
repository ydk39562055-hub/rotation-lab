# -*- coding: utf-8 -*-
"""
판정 창(모멘텀 형성기간) 비교 백테스트 — "63일 대신 3~12개월 창이면 예측력이 생기나?"

방법:
- 섹터만 사용 (미국 11 SPDR + 한국 10 KODEX — 구성 고정, 사후선택 편향 없음)
- 매주 스냅샷: 각 '창 설정'으로 점수 산출 → 유니버스 내 순위
- ★진입 = 다음 거래일. 성과 = 이후 21/63/126 거래일 수익률 (유니버스 내 상대 비교)
- 핵심 지표:
  · 스프레드 = 상위3 평균수익 − 하위3 평균수익  (벤치마크 무관, 순수 순위 예측력)
  · 상위3 승률 = 상위3 중 유니버스 중앙값을 이긴 비율
  · IC = 점수순위 ↔ 미래수익 순위의 상관 (스피어만), 평균과 양(+)인 주 비율
- 비교 대상이 같은 데이터·같은 시점이라 설정 간 우열은 공정.

한계: 주간 스냅샷 중첩(n 과대) / 미국은 11개·한국은 10개뿐이라 상위3=27%로 거친 구분.
"""
import os, sys, io
import numpy as np
import pandas as pd
def _spearman(a, b):
    """스피어만 순위상관 (scipy 없이)."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
from fetch import load_config  # noqa: E402

CACHE = os.path.join(HERE, "data", "backtest_prices.pkl")
STEP = 5
WARMUP = 280            # 252+21 창 + 여유
HORIZONS = (21, 63, 126)
TOPK = 3

# (이름, 점수 함수) — s는 t까지 잘린 종가 시리즈(dropna 완료)
def _r(s, n, skip=0):
    """skip 거래일 전 시점 기준 n거래일 수익률. 데이터 부족 시 NaN."""
    if len(s) < n + skip + 1:
        return np.nan
    end = s.iloc[-1 - skip]
    start = s.iloc[-1 - skip - n]
    return float(end / start - 1.0)

CONFIGS = [
    ("현행(63·21·5 혼합)", lambda s: (np.nan if any(np.isnan(x) for x in
        (_r(s,63), _r(s,21), _r(s,5))) else 0.5*_r(s,63)+0.3*_r(s,21)+0.2*_r(s,5))),
    ("3개월(63)",        lambda s: _r(s, 63)),
    ("6개월(126)",       lambda s: _r(s, 126)),
    ("12개월(252)",      lambda s: _r(s, 252)),
    ("12-1(252, 최근1달 제외)", lambda s: _r(s, 231, skip=21)),
    ("6-1(126, 최근1달 제외)",  lambda s: _r(s, 105, skip=21)),
    ("혼합 장기(126·63·21)", lambda s: (np.nan if any(np.isnan(x) for x in
        (_r(s,126), _r(s,63), _r(s,21))) else 0.5*_r(s,126)+0.3*_r(s,63)+0.2*_r(s,21))),
]


def fwd_ret(close, tk, t, h):
    s = close[tk].dropna()
    pos = s.index.searchsorted(t, side="right")
    if pos + h >= len(s):
        return np.nan
    return float(s.iloc[pos + h] / s.iloc[pos] - 1.0) * 100.0


def run():
    store = pd.read_pickle(CACHE)
    close = store["close"]
    sectors, _ = load_config()
    universes = {"us섹터": list(sectors.get("us", {}).values()),
                 "kr섹터": list(sectors.get("kr", {}).values())}

    spy = close["SPY"].dropna()
    snaps = spy.index[WARMUP::STEP]
    print(f"[스냅샷] {len(snaps)}개 주간 ({snaps[0].date()} ~ {snaps[-1].date()})\n")

    for uni, tks in universes.items():
        tks = [tk for tk in tks if tk in close.columns]
        # 결과 누적: config → h → dict(spread[], top_win[], top_ex[], ic[])
        acc = {cfg: {h: {"spread": [], "twin": [], "tex": [], "ic": []}
                     for h in HORIZONS} for cfg, _ in CONFIGS}

        for t in snaps:
            cut = {tk: close[tk].loc[:t].dropna() for tk in tks}
            fwd = {h: {tk: fwd_ret(close, tk, t, h) for tk in tks} for h in HORIZONS}
            for cfg, fn in CONFIGS:
                scores = {tk: fn(cut[tk]) for tk in tks}
                valid = [tk for tk in tks if not np.isnan(scores[tk])]
                if len(valid) < 8:
                    continue
                ranked = sorted(valid, key=lambda x: -scores[x])
                for h in HORIZONS:
                    fr = {tk: fwd[h][tk] for tk in valid if not np.isnan(fwd[h][tk])}
                    if len(fr) < 8:
                        continue
                    rk = [tk for tk in ranked if tk in fr]
                    top, bot = rk[:TOPK], rk[-TOPK:]
                    med = float(np.median(list(fr.values())))
                    a = acc[cfg][h]
                    a["spread"].append(np.mean([fr[x] for x in top]) - np.mean([fr[x] for x in bot]))
                    a["twin"].extend([1.0 if fr[x] > med else 0.0 for x in top])
                    a["tex"].extend([fr[x] - med for x in top])
                    ic = _spearman([scores[x] for x in rk], [fr[x] for x in rk])
                    if not np.isnan(ic):
                        a["ic"].append(ic)

        print("=" * 86)
        print(f" {uni} — 창 설정별 순위 예측력 (상위3 vs 하위3, 진입=다음 거래일)")
        print("=" * 86)
        print(f"  {'설정':<22}{'지평':>5}{'스프레드':>9}{'양(+)주':>8}{'상위3승률':>9}{'상위3초과':>10}{'IC':>7}{'IC>0':>6}")
        for cfg, _ in CONFIGS:
            for h in HORIZONS:
                a = acc[cfg][h]
                if not a["spread"]:
                    continue
                sp = np.mean(a["spread"])
                sp_pos = np.mean([1 if x > 0 else 0 for x in a["spread"]]) * 100
                twin = np.mean(a["twin"]) * 100
                tex = np.mean(a["tex"])
                ic = np.mean(a["ic"])
                icp = np.mean([1 if x > 0 else 0 for x in a["ic"]]) * 100
                print(f"  {cfg:<22}{h:>4}d{sp:>+8.2f}%{sp_pos:>7.0f}%{twin:>8.0f}%{tex:>+9.2f}%{ic:>+7.3f}{icp:>5.0f}%")
            print()

    print("[읽는 법] 스프레드>0 & 양(+)주>55% & IC>0 가 꾸준해야 '모멘텀 실재'.")
    print("          상위3승률은 유니버스 중앙값 대비. 50%=동전던지기.")


if __name__ == "__main__":
    run()
