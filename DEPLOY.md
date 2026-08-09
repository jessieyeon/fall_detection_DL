# 배포 가이드 — 온라인 전시 URL 제출용

목표: **HTTPS 공개 URL** 하나. 전시 사이트가 그 URL을 `<iframe>`으로 띄웁니다.

> URL이 브라우저에서 열리는 것과 **iframe 안에서 도는 것은 다른 문제**입니다.
> 반드시 §4의 iframe 검증까지 마치세요. 제출 직전에 발견하면 손쓸 시간이 없습니다.

---

## 1. 사전 준비

### 필요한 것

- GitHub 저장소 (Railway/Render가 여기서 빌드합니다)
- **RAM 1~2GB 인스턴스.** 무료 티어(512MB)로는 안 됩니다 — torch + ultralytics가 안 들어갑니다
- 카드 등록 (Railway/Render 모두 월 $5~7)

### 이미지 크기에 대해

이 Dockerfile은 세 가지로 크기를 줄였습니다.

| 조치 | 효과 |
|---|---|
| CPU 전용 torch wheel | 2.5GB → 800MB |
| `face_recognition` 제거 (→ `requirements-local.txt`) | dlib 소스 빌드 제거, 빌드 실패 위험 해소 |
| `opencv-contrib` → `opencv-python-headless` | GUI 라이브러리 의존 제거 |

`.dockerignore`로 데이터셋·학습 산출물(수 GB)도 빌드 컨텍스트에서 뺐습니다.

---

## 2. 로컬 Docker는 선택 사항

**Railway/Render가 자기 인프라에서 Dockerfile을 직접 빌드합니다.** 로컬에 Docker가
없어도 배포할 수 있습니다. GitHub에 푸시하면 끝이에요.

| | 로컬 Docker 있음 | 없음 (바로 클라우드) |
|---|---|---|
| 빌드 실패 시 반복 | 수 분 | 회당 10~20분 |
| 초기 설치 | Docker Desktop ~2GB | 없음 |
| 권장 | 시간 여유 있을 때 | **마감이 급할 때** |

마감이 8/17이라면 **바로 클라우드로 가는 편**을 권합니다. 빌드 로그가 실시간으로
보이므로 실패해도 원인은 알 수 있습니다.

### 로컬에서 코드만 확인 (Docker 없이)

컨테이너 없이도 앱이 도는지는 확인할 수 있습니다.

```bash
cd ~/Desktop/fall_detection_DL
cd webservice/frontend && npm install && npm run build && cd ../..
python3 -m webservice.seed
DAON_SKIP_WARMUP=1 python3 -m uvicorn webservice.app:app --port 8000
```

`http://localhost:8000` → 로그인(`senior@daon.com` / `pw`) → 컨설팅 업로드까지
되면 코드는 정상입니다. 남은 변수는 컨테이너 빌드뿐입니다.

### 로컬 Docker를 쓴다면

```bash
docker build -t daon .
docker run -p 8000:8000 -e DAON_SECRET=local-test daon
```

첫 빌드는 10~20분 걸립니다 (torch 다운로드).

---

## 3. 배포

### Railway

1. railway.app → New Project → Deploy from GitHub repo
2. Dockerfile을 자동 감지합니다
3. Settings → Networking → **Generate Domain** (여기서 나온 URL을 제출)
4. Variables 탭에서 §5의 환경변수 설정
5. Settings → Resources에서 메모리 2GB 확인

### Render

1. render.com → New → Web Service → 저장소 연결
2. Runtime: **Docker**
3. Instance Type: **Starter 이상** (Free는 512MB라 불가)
4. Environment에서 §5의 환경변수 설정

---

## 4. iframe 검증 — 건너뛰지 말 것

배포 URL이 나오면 **반드시** 이걸 하세요.

```bash
# 배포 URL을 넣어서 테스트 페이지 생성
python3 scripts/make_iframe_test.py https://your-app.up.railway.app
open iframe_test.html
```

체크할 것:

- [ ] iframe 안에 화면이 뜬다 (빈 화면이면 CSP/X-Frame-Options 문제)
- [ ] iframe 안에서 **로그인이 되고 유지된다** ← 가장 잘 놓치는 부분
- [ ] 컨설팅 영상 업로드 → 리포트까지 iframe 안에서 완주
- [ ] 브라우저 콘솔에 에러가 없다

**로그인이 iframe 안에서만 안 된다면** `DAON_EMBED=1`이 설정되지 않은 것입니다.
iframe 안에서 우리 쿠키는 서드파티 쿠키가 되고, 기본값(`SameSite=lax`)에서는
브라우저가 아예 보내지 않습니다. `DAON_EMBED=1`이 `SameSite=None; Secure`로 바꿔줍니다.

모바일 실기기(iOS Safari, Android Chrome)에서도 같은 페이지를 열어 확인하세요.
iOS Safari는 서드파티 쿠키에 특히 엄격합니다.

---

## 5. 환경변수

| 변수 | 값 | 설명 |
|---|---|---|
| `DAON_SECRET` | 임의의 긴 문자열 | **필수.** 세션 서명 키. 기본값이 `dev-demo-secret-change-me`라 그대로 두면 세션 위조가 가능합니다 |
| `DAON_EMBED` | `1` | **필수.** iframe용 쿠키 설정(`SameSite=None; Secure`) |
| `DAON_FRAME_ANCESTORS` | `*` 또는 전시 사이트 도메인 | 임베드 허용 대상. 도메인을 알게 되면 좁히세요 |
| `PORT` | (플랫폼이 자동 주입) | 건드리지 마세요 |

### 성능·방어 (기본값으로 두어도 동작)

| 변수 | 기본 | 설명 |
|---|---|---|
| `DAON_ANALYZE_FPS` | `3` | 초당 몇 프레임을 분석할지 |
| `DAON_YOLO_IMGSZ` | `384` | YOLO 입력 크기. 검출률이 낮으면 올리세요 |
| `DAON_YOLO_MODEL` | `yolo11n.pt` | 모델 |
| `DAON_ANALYZE_MAX_SECONDS` | `90` | 영상 앞부분만 분석 |
| `DAON_MAX_UPLOAD_MB` | `200` | 업로드 크기 상한. 아이폰 1분 영상이 100~150MB라 넉넉히 잡았습니다. 업로드는 청크로 디스크에 흘려 쓰므로 이 값이 메모리를 늘리진 않습니다 |
| `DAON_MAX_CONCURRENT_JOBS` | `2` | 동시에 실행되는 분석 수 |
| `DAON_MAX_INFLIGHT_JOBS` | `8` | 대기 포함 총량. 넘으면 503으로 거절 |
| `DAON_TURN_WEIGHT` | `2.5` | 회전 지점 가중치 |
| `DAON_TRANSCODE_LONG_EDGE` | `720` | 변환 시 축소할 긴 변 |
| `DAON_SKIP_WARMUP` | (미설정) | `1`이면 기동 시 모델 사전 로딩 생략 |

`DAON_SECRET` 생성:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 6. SQLite 영속성 — 주의

`webservice/daon.db`는 **컨테이너 파일시스템**에 있습니다. 재배포하거나 인스턴스가
재시작되면 사라집니다.

- **데모 계정**은 기동 시 `python -m webservice.seed`가 다시 만들어주므로 괜찮습니다
- **생성된 리포트와 보호자 매칭은 사라집니다**

전시 기간 동안 유지하려면 영구 볼륨을 붙이세요.

- Railway: Settings → Volumes → Mount path `/app/webservice`
- Render: Disks → Mount path `/app/webservice`

리포트 이미지(`webservice/consulting/reports/`)도 같은 경로 아래라 함께 보존됩니다.

작업 G(결과 캐싱)를 마치면 샘플 영상 3개의 리포트는 코드에 포함되므로,
휘발되어도 체험 자체는 계속 됩니다.

---

## 7. 트래픽 관리

전시 조건에 "트래픽 초과로 인한 서버 다운 시 체험 기능이 중단될 수 있다"고
명시되어 있습니다. 현재 방어선:

- 업로드 크기 상한 (`DAON_MAX_UPLOAD_MB`, 기본 80MB)
- 분석 길이 상한 (`DAON_ANALYZE_MAX_SECONDS`, 기본 90초)
- 변환 타임아웃 (`DAON_TRANSCODE_TIMEOUT`, 기본 120초)
- 모델을 프로세스당 1회만 로드 (요청마다 재로딩하지 않음)

- **동시 분석 2개, 대기 포함 8개 상한** — 초과하면 503으로 거절합니다.
  응답 없이 기다리게 하는 것보다 "지금 혼잡하니 잠시 후"가 낫습니다
- **샘플 영상 결과 캐싱** — 아래 참고

### 샘플 캐싱 (영상 준비되면 실행)

체험용 AI 영상 3개를 미리 분석해두면, 관람객이 그 영상을 올릴 때 **분석 없이
즉시** 결과가 나옵니다. 대기 0초 + 서버 부하 거의 0입니다.

```bash
# 영상을 webservice/frontend/public/samples/ 에 넣고
#   unit.mp4 / lounge.mp4 / corridor.mp4
python3 scripts/build_samples.py --auto
```

`webservice/consulting/samples/` 에 리포트·이미지·매니페스트가 생기고, 서버가
업로드 파일의 SHA-256을 보고 자동으로 맞춥니다. **파일명이 아니라 내용 해시**라
관람객이 이름을 바꿔 올려도 걸립니다.

캐시에 없는 영상은 지금까지처럼 실제 분석을 탑니다 — 부스에서 관람객 영상을
분석해주는 것도 그대로 됩니다.

> 영상을 다시 만들면 해시가 바뀌므로 스크립트를 다시 돌려야 합니다.
> 생성물은 저장소에 커밋해야 배포 이미지에 포함됩니다.

분석 작업은 `jobs.py`의 인메모리 딕셔너리 + 스레드로 돌아갑니다. 단일 프로세스
전제이므로 **uvicorn 워커를 여러 개 띄우면 안 됩니다** (작업 상태가 워커 간에
공유되지 않아 폴링이 404를 받습니다).

---

## 8. 자주 겪는 문제

**빌드가 메모리 부족으로 죽는다**
→ 빌드 인스턴스 메모리를 올리거나, 로컬에서 빌드해 이미지 레지스트리에 푸시하세요.

**`ImportError: libGL.so.1`**
→ `opencv-contrib-python`이 설치된 것입니다. `requirements.txt`에 headless만 있는지 확인하세요.

**컨설팅 첫 요청이 오래 걸린다**
→ 워밍업이 아직 안 끝난 것입니다. 로그에 `[warmup] YOLO 모델 준비 완료`가 찍히는지 보세요.

**"영상을 열 수 없습니다"**
→ 컨테이너에 ffmpeg가 없습니다. Dockerfile의 `apt-get install ffmpeg` 줄을 확인하세요.

**iframe은 뜨는데 로그인만 안 된다**
→ `DAON_EMBED=1` 누락. §4 참고.
