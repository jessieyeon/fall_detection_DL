# 다온 시연 준비 런북

## 큰 그림 — 시연 때 동시에 도는 것들

```
┌─ 맥북 ────────────────────────────────────────────────┐
│                                                        │
│  [1] 플랫폼 (웹앱)          [2] 감지 파이프라인          │
│   uvicorn :8000   ◀──POST──  main.py + 카메라 [+아두이노] │
│   (API+WS+빌드된 프런트)      (실시간 스켈레톤/타일 중계)  │
│      │                                                 │
│      └── 외부 데이터: 카카오 키 · 평면도 · 샘플영상 · YOLO │
└────────────────────────────────────────────────────────┘
        ▲
   폰/브라우저(관객): 로그인 → 마이페이지/컨설팅/실시간중계
```

- **[1] 플랫폼**은 관객이 보는 웹앱. 4개 기능(설문·보호자매칭·컨설팅·실시간중계)을 서빙.
- **[2] 감지 파이프라인**은 실시간 중계에 실제 카메라 데이터를 흘려보내는 소스. 실시간 기능을 "진짜"로 보여줄 때만 필요.
- 컨설팅/병원/평면도는 [1]만으로 돈다(외부 에셋 필요).

---

## Phase A — 설치 (최초 1회)

### A1. 파이썬 의존성
```bash
pip install -r requirements.txt
```
- **왜**: 플랫폼(fastapi/uvicorn), 컨설팅(ultralytics=YOLO, torch 포함), 업로드(python-multipart)가 다 여기 있음.
- **결과**: 모든 임포트 성공. `python3 -m pytest -q` → 847 passed.
- **주의**: `ultralytics`가 `torch`를 끌어와서 수백 MB~1GB 다운로드. 시간 넉넉히. GPU 없는 맥이면 컨설팅 분석이 느림(아래 D5 참고).

### A2. 프런트엔드 의존성
```bash
cd webservice/frontend && npm install
```
- **왜**: React 앱을 dev 서버로 띄우거나 빌드하려면 필요.
- **결과**: `node_modules/` 생성. `npm run build` 가 에러 없이 돎.

---

## Phase B — 외부 에셋·키 준비

### B1. 카카오 REST API 키 (근처 병원용)
1. https://developers.kakao.com 로그인 → 내 애플리케이션 → 애플리케이션 추가
2. 앱 → "앱 키" → **REST API 키** 복사
3. (플랫폼 실행 터미널에서) `export KAKAO_REST_KEY=<복사한 키>`
- **왜**: P2 "근처 병원 찾기"가 카카오 로컬 API로 실검색. 키 없으면 그 버튼은 503.
- **결과**: 마이페이지 "근처 병원 찾기" → 어르신 주소 근처 실제 병원 목록.
- **비용**: 무료(일 10만 호출). 데모엔 무제한이나 다름없음.

### B2. 평면도 이미지 (우리 집)
- 시연 아파트의 평면도 이미지를 구해서 이 경로에 저장(파일명 그대로):
  `webservice/data/floorplans/demo_apartment.png`
- **왜**: 시드된 어르신 계정의 `apartment_name="다온아파트"` → 매니페스트가 `다온아파트 → demo_apartment.png` 로 매칭. 지금은 1×1 투명 자리표시자라 사실상 안 보임.
- **결과**: 마이페이지 "우리 집"에 진짜 평면도가 뜸.
- **다른 아파트로 하려면**: `webservice/data/floorplans/manifest.json` 에 `"아파트명":"파일명"` 추가하고, 시드된 어르신의 `apartment_name`도 그 이름으로 맞춰야 함(말해주면 시드 수정해줄게).

### B3. 샘플 집 생활 영상 (컨설팅용)
- 어르신이 집 안을 돌아다니는 영상 1개(짧게, 10~30초 권장). 위에서 비스듬히 내려보는 각도가 히트맵이 예쁨.
- **왜**: P3 컨설팅이 이 영상을 YOLO로 분석해 체류 히트맵을 만듦.
- **결과**: 컨설팅 업로드 → 히트맵 이미지 + 위험 구역 권고 리포트.
- **팁**: 짧을수록 분석이 빠름. 시연 전에 한 번 미리 분석해두면(캐시) 당일 안정적.

---

## Phase C — 환경변수 · 데이터 시드

### C1. 환경변수 (플랫폼 터미널)
```bash
export KAKAO_REST_KEY=<B1 키>
export DAON_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(16))")   # 선택(로컬은 없어도 됨)
# LIVE_INGEST_TOKEN 은 기본 "daon-live" 로 둬도 됨(플랫폼·파이프라인 양쪽이 같은 값이면 OK)
```
- **왜**: 카카오 병원, 세션 서명 시크릿, 실시간 인제스트 토큰.
- **결과**: 병원 검색 작동 / 세션 안전 / 실시간 중계 인제스트 허용.
- **주의**: `KAKAO_REST_KEY`는 **플랫폼(uvicorn) 터미널**에만 있으면 됨. `LIVE_INGEST_TOKEN`을 커스텀으로 바꾸면 플랫폼과 `main.py`/`live_demo` **양쪽 다** 같은 값으로 export 해야 함.

### C2. 시연 계정 시드
```bash
python3 -m webservice.seed
```
- **왜**: 어르신(`senior@daon.com`/`pw`)·보호자(`guardian@daon.com`/`pw`) 계정 생성 + 어르신 주소/아파트("다온아파트") 채움.
- **결과**: 로그인 가능 + 병원 검색이 쓸 주소가 생김. (멱등 — 여러 번 실행해도 안전)

---

## Phase D — 리허설 (기능별 확인, 시연 전날 권장)

### D0. 단일 서버 (빌드 1회 + uvicorn 하나)
```bash
# (1) 프런트 빌드 — 한 번만. 코드 바뀔 때만 다시.
cd webservice/frontend && npm run build
# (2) 루트로 돌아와 서버 하나만 (KAKAO_REST_KEY 여기 export 되어 있어야 함)
cd /Users/Yeon/Desktop/fall_detection_DL
python3 -m uvicorn webservice.app:app --host 0.0.0.0 --port 8000
```
- **왜**: `app.py`가 빌드된 `dist/`를 직접 서빙하므로 vite 불필요. 터미널·포트 하나로 끝(vite 느린 기동·프록시·두 서버 꼬임 없음). `--host 0.0.0.0`은 폰 접속용.
- **결과**: 브라우저에서 `http://localhost:8000` → 로그인 화면. (5173 아님!)
- **주의**: `dist/`는 git에 안 올라가므로 새 환경/코드 변경 시 `npm run build`를 먼저.

### D1. 로그인 → 마이페이지
- `senior@daon.com` / `pw` → 마이페이지에 4개 섹션 + 컨설팅/실시간 링크.

### D2. 설문 (자가진단)
- "설문 하기" → 응답 → 제출 → 등급(낮음/보통/높음) 표시·저장.

### D3. 보호자 매칭 (창 2개 필요)
- 어르신 창: "연결 코드 생성" → 6자리 코드
- 보호자 창(다른 브라우저/시크릿창에 `guardian@daon.com`/`pw`): 코드 입력 → "김할머니 — 자가진단 등급: …" 열람.
- **왜**: 크로스 계정 연동을 보여주는 핵심 장면.

### D4. 병원 (B1 키 필요)
- 마이페이지 "근처 병원 찾기" → 실제 병원 목록.

### D5. 컨설팅 ★ 타이밍 리허설 필수
- 컨설팅 페이지 → 샘플 영상 업로드 → "분석 중…" → 히트맵+리포트.
- **왜 리허설**: YOLO가 CPU에서 느림(영상 길이×해상도에 비례, 수십 초~수 분). 처음엔 `yolo11m.pt`(~40MB)도 자동 다운로드됨.
- **대비**: (a) 샘플을 짧게, (b) 시연 전 미리 한 번 돌려 결과를 만들어두면 "지난 리포트"에서 즉시 열림, (c) 히트맵이 이상하면 규칙 임계값(`webservice/consulting/rules.py`의 0.66/0.33)·격자(3×3) 조정 — 말해주면 같이 튜닝.

### D6. 평면도 (B2 이미지 필요)
- 마이페이지 "우리 집"에 진짜 평면도 표시.

### D7. 실시간 중계 ★ 두 단계로
- **카메라 없이(안전한 백업)**: 서버 켠 상태에서
  ```bash
  python3 -m webservice.live_demo
  ```
  → 브라우저 `/live`에 합성 스켈레톤이 움직이고 낙상 시 타일이 붉어짐.
  - **왜**: 카메라/조명/각도 문제 없이 실시간 UI를 100% 재현. 시연 백업으로 항상 준비.
- **진짜 카메라(파이프라인 연결)**:
  ```bash
  python3 main.py 0 --live-url http://localhost:8000            # 웹캠
  # 또는 python3 main.py test_videos/S01T23R01_.mp4 --live-url http://localhost:8000
  ```
  → `/live`에 실제 카메라의 스켈레톤·발사 타일 중계.
  - **왜 각도 주의**: 방향 판정·타일 발사는 카메라가 **높은 곳에서 비스듬히 바닥을 내려봐야** 제대로 나옴(README 참고). 정면/눈높이면 방향이 다 "가까움"으로 붕괴.
  - **중요**: `/live` 캔버스는 **보이는 브라우저 탭**에서만 그려짐(백그라운드 탭은 렌더 멈춤). 시연 창을 앞에 두기.

### D8. (선택) 아두이노 물리 타일
```bash
python3 main.py 0 --live-url http://localhost:8000 --port /dev/cu.usbmodemXXXX
```
- **왜**: 실제 서보로 충격완화 타일을 떨어뜨리는 원래 하드웨어 데모.
- **주의**: 4개 동시 발사는 전원 용량 필요(README). 웹 데모만이면 생략 가능.

---

## Phase E — 시연 당일 실행 순서 (최소, 단일 서버)

사전(전날): `cd webservice/frontend && npm run build` 한 번.

1. 터미널1 (루트): `export KAKAO_REST_KEY=...` → `python3 -m webservice.seed` → `python3 -m uvicorn webservice.app:app --host 0.0.0.0 --port 8000`
2. (실시간 진짜로) 터미널2 (루트): `python3 main.py 0 --live-url http://localhost:8000`
   - 또는 백업으로 `python3 -m webservice.live_demo`
3. 브라우저 `http://localhost:8000` → 시연.
4. 폰으로 볼 거면: 같은 WiFi + `http://<맥북 LAN IP>:8000` (이미 `--host 0.0.0.0`이라 바로 됨).

---

## 정직한 리스크 / 알아둘 것

- **단일 서버로 합침(완료)**: `app.py`가 빌드된 프런트를 서빙 → uvicorn 하나(`localhost:8000`)만 켜면 됨. 개발 중 HMR이 필요하면 예전처럼 vite(`npm run dev`)를 따로 써도 되지만, 시연은 빌드+단일서버가 안정적.
- **컨설팅 속도**: CPU YOLO라 느림. 반드시 리허설 + 미리 캐시.
- **실시간 캔버스**: 보이는 브라우저 탭에서만 렌더.
- **폰 접속**: vite를 `--host`로 띄우고 방화벽/같은 WiFi 확인.
- **데모 시크릿/토큰**: 로컬 시연은 기본값으로 충분. 외부 배포는 절대 금지(레저의 DEPLOY-PREP 참고).
- **남은 소소한 부채**(시연 무관): P1 create_user 에러 라벨, 업로드 파일 정리 등 — `.superpowers/sdd/progress.md`에 기록됨.
```
