# -*- coding: utf-8 -*-
"""
디스코드 전송(선택). 매일 아침 TOP 요약을 푸시한다.
웹훅 주소는 다음 중 하나로 설정:
  1) 환경변수 DISCORD_WEBHOOK_URL
  2) config/discord.json  →  {"webhook": "https://discord.com/api/webhooks/..."}
설정이 없으면 조용히 건너뛴다(에러 아님). 대시보드 HTML 파일도 함께 첨부한다.
"""
import os, json
import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _webhook():
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if url:
        return url
    cfg = os.path.join(HERE, "config", "discord.json")
    if os.path.exists(cfg):
        try:
            with open(cfg, encoding="utf-8") as f:
                return json.load(f).get("webhook", "").strip()
        except Exception:
            return ""
    return ""


def _top_lines(rows, k=5):
    out = []
    for r in rows[:k]:
        arrow = ""
        d = r.get("delta1")
        if d:
            arrow = f" ({'▲' if d > 0 else '▼'}{abs(d)})"
        rot = " 🔄" if r.get("rotation") else ""
        rs126 = r.get("rs126")
        rs126s = "—" if rs126 is None or rs126 != rs126 else f"{rs126:+.1f}"
        out.append(f"`{r['rank']}.` {r['name']}{arrow}{rot}  · RS126 {rs126s}")
    return "\n".join(out) if out else "_데이터 없음_"


def alert(title, message):
    """파이프라인 실패·푸시 실패 등 운영 경고를 디스코드로 보낸다.
    웹훅 미설정이면 콘솔 출력만 하고 넘어간다."""
    url = _webhook()
    if not url:
        print(f"[경고알림] 웹훅 미설정 → 콘솔만: {title} / {message}")
        return False
    embed = {
        "title": f"🚨 {title}",
        "description": str(message)[:3900],
        "color": 0xFF5D6C,
        "footer": {"text": "theme-rotation 운영 경고"},
    }
    try:
        resp = requests.post(url, json={"embeds": [embed]}, timeout=15)
        ok = resp.status_code in (200, 204)
        print(f"[경고알림] 전송 {'성공' if ok else '실패('+str(resp.status_code)+')'}")
        return ok
    except Exception as e:
        print(f"[경고알림] 전송 오류: {e}")
        return False


def send(comp_result, failures, dashboard_path=None):
    url = _webhook()
    if not url:
        print("[디스코드] 웹훅 미설정 → 전송 건너뜀 (HTML 대시보드만 생성)")
        return False

    date = comp_result["date"]
    rotations = [r["name"] for r in comp_result["themes"] if r.get("rotation")]
    desc = (
        f"**🔥 테마 TOP5**\n{_top_lines(comp_result['themes'])}\n\n"
        f"**🇺🇸 섹터 TOP5**\n{_top_lines(comp_result['us'])}\n\n"
        f"**🇰🇷 섹터 TOP3**\n{_top_lines(comp_result['kr'], 3)}"
    )
    if rotations:
        desc += f"\n\n**🔄 로테이션 후보**\n{', '.join(rotations)}"
    if failures:
        desc += f"\n\n⚠️ 수집 실패 {len(failures)}: {', '.join(failures[:10])}"

    embed = {
        "title": f"📡 로테이션 랩 · ROTATION LAB · {date}",
        "description": desc[:4000],
        "color": 0x27C498,
        "footer": {"text": "theme-rotation · 첨부된 dashboard.html 을 열면 전체 표·RRG 확인"},
    }
    payload = {"embeds": [embed]}

    try:
        if dashboard_path and os.path.exists(dashboard_path):
            with open(dashboard_path, "rb") as f:
                files = {
                    "payload_json": (None, json.dumps(payload)),
                    "file": ("dashboard.html", f, "text/html"),
                }
                resp = requests.post(url, files=files, timeout=20)
        else:
            resp = requests.post(url, json=payload, timeout=20)
        ok = resp.status_code in (200, 204)
        print(f"[디스코드] 전송 {'성공' if ok else '실패('+str(resp.status_code)+')'}")
        return ok
    except Exception as e:
        print(f"[디스코드] 전송 오류: {e}")
        return False
