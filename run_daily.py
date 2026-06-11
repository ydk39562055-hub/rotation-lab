# -*- coding: utf-8 -*-
"""
전체 파이프라인 1회 실행: 수집 → 계산 → RRG → HTML → (디스코드).
사용:
  python run_daily.py            # 수집·계산·HTML 생성(+디스코드 웹훅 있으면 전송)
  python run_daily.py --open     # 끝나고 기본 브라우저로 대시보드 열기
  python run_daily.py --no-discord
"""
import os, sys, io, traceback

# UTF-8 콘솔(윈도우 스케줄러에서 한글 깨짐 방지)
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import fetch, compute, rrg as rrg_mod, report, notify


def publish(dashboard_path):
    """대시보드를 repo 루트 index.html 로 복사하고 GitHub Pages에 푸시(자동 갱신)."""
    import shutil, subprocess
    from datetime import datetime
    index = os.path.join(HERE, "index.html")
    shutil.copyfile(dashboard_path, index)
    if not os.path.isdir(os.path.join(HERE, ".git")):
        print("[배포] git 저장소 아님 → index.html만 갱신")
        return
    try:
        subprocess.run(["git", "-C", HERE, "add", "index.html", "strong_themes.json"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", HERE, "commit", "-m", f"update {datetime.now():%Y-%m-%d %H:%M}"],
                       capture_output=True, text=True)
        r = subprocess.run(["git", "-C", HERE, "push"], capture_output=True, text=True)
        print("[배포] GitHub Pages 푸시 완료" if r.returncode == 0 else f"[배포] 푸시 실패: {r.stderr[:200]}")
    except Exception as e:
        print(f"[배포] 건너뜀: {e}")


def main():
    args = sys.argv[1:]
    do_open = "--open" in args
    do_discord = "--no-discord" not in args
    do_publish = "--no-publish" not in args

    print("=" * 50)
    print(" 테마·섹터 로테이션 — 일일 파이프라인 시작")
    print("=" * 50)

    prices, failures, sectors, themes = fetch.run()
    comp_result = compute.run(prices, sectors, themes)
    rrg_data = rrg_mod.run(prices, comp_result, sectors, themes)
    path = report.write(comp_result, rrg_data, failures)

    print(f"\n[리포트] 생성 → {path}")
    print(f"  테마 {len(comp_result['themes'])} · 미국섹터 {len(comp_result['us'])} · 한국섹터 {len(comp_result['kr'])}")
    if comp_result["themes"]:
        print("  [테마 TOP3]")
        for r in comp_result["themes"][:3]:
            c = r["composite"]
            print(f"    {r['rank']}. {r['name']}  종합 {('%.2f'%c) if c==c else '—'}")

    if do_publish:
        try:
            publish(path)
        except Exception as e:
            print(f"[배포] 예외 무시: {e}")

    if do_discord:
        try:
            notify.send(comp_result, failures, dashboard_path=path)
        except Exception as e:
            print(f"[디스코드] 예외 무시: {e}")

    if do_open:
        import webbrowser
        webbrowser.open("file:///" + path.replace("\\", "/"))

    print("\n완료.")
    return path


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
