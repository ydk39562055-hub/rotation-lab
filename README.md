# 📡 theme-rotation — 테마·섹터 로테이션 랭킹 대시보드

매일 아침 자동 실행되어 **미국 섹터 + 내 커스텀 테마** 중 지금 자금이 몰리는 곳을
상대강도(RS) 순위표 + RRG 차트로 보여주는 도구.

---

## 1. 빠른 시작

```bat
cd theme-rotation
py -m pip install -r requirements.txt
py run_daily.py --open
```

끝나면 `output/dashboard.html` 이 생기고 브라우저로 열린다.
(처음 한 번은 종목 일봉을 전부 받느라 몇 분 걸리고, 이후엔 증분 수집이라 빠르다.)

---

## 2. 테마 채우기 (가장 먼저 할 일)

`config/themes.json` 을 연다. 더미 2개(`반도체`, `빅테크`)는 동작 확인용이다.

```json
{
  "AI 인프라": ["NVDA", "AVGO", "VRT", "SMCI"],
  "전력/원자력": ["VST", "CEG", "NRG", "SMR"],
  ...
}
```

- 미국 종목: 접미사 없이 `NVDA`
- 한국 종목: `.KS`(코스피) / `.KQ`(코스닥) → 예) 삼성전자 `005930.KS`
- 빈 배열 `[]` 인 테마는 자동으로 건너뛴다.
- 섹터 ETF 목록은 `config/sectors.json` 에서 수정.

> 티커가 틀리면 수집 단계에서 건너뛰고 대시보드 상단 + `data/run.log` 에 실패 목록으로 남는다. 전체가 멈추지 않는다.

---

## 3. 자동 실행 (무인) — 윈도우 작업 스케줄러

### 방법 A. 명령 한 줄로 등록 (PowerShell/CMD)

```cmd
schtasks /create /tn "ThemeRotation" /tr "\"%CD%\run_daily.bat\"" /sc daily /st 08:00 /f
```

- 매일 **오전 8시** 실행 (미국 전일 종가 반영 완료 시점).
- 시간 바꾸려면 `/st 08:00` 수정.
- 노트북이 꺼져 있으면 그 시간엔 못 돈다 → 켜진 다음 한 번 수동 실행하거나, 작업 스케줄러에서 "놓친 작업 실행" 옵션을 켠다.

### 방법 B. GUI

1. `Win` → "작업 스케줄러" 실행
2. 오른쪽 **기본 작업 만들기**
3. 트리거: **매일**, 오전 8:00
4. 동작: **프로그램 시작** → 찾아보기로 `run_daily.bat` 선택
5. 마침

### 등록 확인 / 삭제

```cmd
schtasks /query /tn "ThemeRotation"
schtasks /run   /tn "ThemeRotation"   REM 지금 즉시 한 번 실행해보기
schtasks /delete /tn "ThemeRotation" /f
```

실행 기록은 `data/run.log` 에 쌓인다.

---

## 4. 디스코드 알림 (선택)

매일 아침 TOP 요약 + 대시보드 파일을 디스코드로 받는다.

1. 디스코드 채널 → 채널 편집 → 연동(Integrations) → 웹후크 → **새 웹후크** → URL 복사
2. 둘 중 하나로 설정:
   - 환경변수: `setx DISCORD_WEBHOOK_URL "https://discord.com/api/webhooks/..."`
   - 또는 파일 `config/discord.json` 생성:
     ```json
     { "webhook": "https://discord.com/api/webhooks/..." }
     ```
3. 끝. 웹훅이 없으면 알림은 조용히 건너뛰고 HTML만 만든다.

> 디스코드는 HTML을 "웹페이지로" 바로 못 띄우고 파일 첨부로 보낸다.
> 폰에서 링크 클릭 한 번으로 열고 싶으면 → 5번(GitHub Pages) 참고.

---

## 5. (선택) 폰에서 웹으로 열기 — GitHub Pages

`output/dashboard.html` 을 GitHub Pages repo에 올리면 `https://...` 주소가 생긴다.
폰에서 그 주소를 열고 "홈 화면에 추가"하면 앱처럼 쓸 수 있다.
(거래일지·매크로 대시보드와 같은 방식. 원하면 자동 푸시까지 붙일 수 있음.)

---

## 6. 지표 읽는 법

| 항목 | 뜻 |
|---|---|
| **RS5 / RS21 / RS63** | 5·21·63 거래일 동안 벤치마크보다 얼마나 더(덜) 올랐나 (×100). 양수=벤치마크 초과 |
| **종합점수** | 0.5·RS63 + 0.3·RS21 + 0.2·RS5 → 이걸로 순위 매김 |
| **테마 RS** | 구성종목 RS의 **중앙값** (평균 아님 — 한두 종목 폭등 왜곡 방지) |
| **breadth** | 테마 내 [52주 신고가 −15% 이내] 종목 비율(%). 높을수록 광범위한 강세 |
| **거래대금흐름** | 최근 5일 평균 거래대금 ÷ 60일 평균. ×1.2↑ = 자금 유입 가속 |
| **전일 / 5일전** | 순위 변화 ▲▼ |
| **🔄 로테이션 후보** | RS63 하위 50% & RS5 상위 20% → 막 돌기 시작한 후보 |

### RRG (4분면)
- **Leading(우상)**: 강하고 더 강해지는 중 — 주도
- **Weakening(우하)**: 강하지만 식는 중 — 차익 구간
- **Lagging(좌하)**: 약하고 더 약해지는 중 — 회피
- **Improving(좌상)**: 약하지만 살아나는 중 — 로테이션 진입 후보

---

## 폴더 구조
```
theme-rotation/
├─ config/  themes.json(내가 채움) · sectors.json · discord.json(선택)
├─ data/    prices/*.parquet(캐시) · history/rankings.json(순위 기록) · run.log
├─ src/     fetch · compute · rrg · report · notify
├─ output/  dashboard.html
├─ run_daily.py · run_daily.bat · requirements.txt
```
