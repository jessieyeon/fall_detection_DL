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
| `DAON_SKIP_SEED` | (미설정) | `1`이면 기동 시 시연 계정 시드 생략. 평소엔 건드리지 마세요 — 시드가 없으면 '체험하기'가 로그인에서 막힙니다 |
| `DAON_DATA_DIR` | (미설정) | DB·업로드·리포트를 둘 경로. 영구 볼륨을 붙였을 때만 설정합니다(§6). 미설정이면 예전대로 `webservice/` 안에 씁니다 |

### 운영 모니터링 (전부 선택 — 비워두면 그 기능만 꺼집니다)

| 변수 | 설명 |
|---|---|
| `SENTRY_DSN` | **서버** 에러 수집. 비우면 Sentry 코드가 아예 안 돕니다 |
| `SENTRY_DSN_FRONTEND` | **브라우저** 에러 수집. 서버와 다른 프로젝트를 쓰면 값이 다릅니다 |
| `SENTRY_ENV` | 기본 `production`. 스테이징을 따로 띄우면 구분값을 주세요 |
| `SENTRY_TRACES_RATE` | 기본 `0.1`. 성능 트레이스 표본 비율(에러는 항상 100%) |
| `POSTHOG_KEY` | 퍼널 분석. PostHog 프로젝트의 Project API Key |
| `POSTHOG_HOST` | 기본 `https://us.i.posthog.com`. EU 프로젝트면 `https://eu.i.posthog.com` |

> **왜 `VITE_` 접두사가 아닌가.** 프런트엔드는 Dockerfile 1단계에서 빌드되는데,
> Vite 는 `import.meta.env.VITE_*` 를 **빌드 시점에** 문자열로 박아 넣습니다.
> 플랫폼 Variables 에 값을 넣어도 빌드 인자로 따로 넘기지 않으면 번들에는 빈
> 값이 들어가고, 배포는 성공하고 에러도 안 나고 데이터만 안 들어옵니다 —
> 제일 알아채기 어려운 형태의 실패입니다. 그래서 서버가 `/api/config` 로
> 런타임에 내려주고, 프런트가 기동 직후 읽어갑니다. **값을 바꾸면 재시작만
> 하면 되고 재빌드가 필요 없습니다.**

`DAON_SECRET` 생성:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 6. SQLite 영속성 — 주의

`webservice/daon.db`는 **컨테이너 파일시스템**에 있습니다. 재배포하거나 인스턴스가
재시작되면 사라집니다.

- **데모 계정**은 기동 시 다시 만들어지므로 괜찮습니다. Dockerfile 의 CMD
  (`python -m webservice.seed`)뿐 아니라 앱 startup 에서도 한 번 더 시드합니다 —
  배포 플랫폼에서 Start Command 를 직접 지정하면 CMD 가 통째로 무시되기 때문입니다
- **생성된 리포트와 보호자 매칭은 사라집니다**

> **DB 가 날아가면 예전 로그인 쿠키가 남아 문제를 일으킵니다.** 세션은 서명된
> 쿠키에만 있고 `DAON_SECRET` 은 그대로라, DB 가 새로 만들어져도 옛 쿠키는 계속
> 유효합니다. 그 안의 사용자 id 는 새 DB 에 없으므로 저장이 전부
> `FOREIGN KEY constraint failed` 로 실패합니다(리포트 저장·어르신 추가·카메라
> 등록이 한꺼번에). 지금은 `routes_auth.current_user` 가 매 요청 세션을 DB 와
> 대조해, 같은 이메일 계정으로 자동 복구하거나 401 로 로그인 화면에 돌려보냅니다.

전시 기간 동안 유지하려면 영구 볼륨을 붙이세요.

> ⚠️ **`/app/webservice` 에 붙이면 안 됩니다.** (예전 이 문서의 안내가 그랬습니다.)
> 그 경로에는 데이터뿐 아니라 **코드가 같이 있습니다** — `app.py`, `routes_*.py`,
> `consulting/*.py`, `frontend/dist` 가 전부 거기입니다. Railway/Render 볼륨은
> 도커의 named volume 과 달리 이미지의 기존 내용을 볼륨으로 복사해주지 않고
> 그냥 **덮어 가립니다.** 빈 볼륨이 코드를 가리므로 서버는
> `ModuleNotFoundError: webservice.app` 로 기동조차 못 하고 재시작을 반복합니다.

데이터만 따로 빠지도록 `DAON_DATA_DIR` 을 두었습니다. 코드가 없는 경로에 볼륨을
붙이고 그 경로를 가리키세요.

1. Railway: Settings → Volumes → Mount path **`/app/data`**
   (Render: Disks → Mount path `/app/data`)
2. Variables 에 `DAON_DATA_DIR=/app/data` 추가
3. 재배포

| | 위치 | 재배포 후 |
|---|---|---|
| `DAON_DATA_DIR` 미설정 (기본) | `webservice/daon.db`, `webservice/consulting/{uploads,reports}` | 사라짐 |
| `DAON_DATA_DIR=/app/data` + 볼륨 | `/app/data/daon.db`, `/app/data/consulting/{uploads,reports}` | **보존됨** |

환경변수를 넣지 않으면 동작이 예전과 완전히 같습니다 — 로컬 개발은 신경 쓸 게 없습니다.

`consulting/samples/`(사전 계산된 샘플 리포트)는 **데이터가 아니라 코드**라 볼륨으로
옮기지 않습니다. 저장소에 커밋돼 이미지에 들어가고, 재배포해도 그대로 있습니다.

> **볼륨을 붙이는 그 배포에서도 기존 데이터는 한 번 날아갑니다.** 볼륨은 빈 채로
> 시작하고, 컨테이너 안에 있던 예전 `daon.db` 를 옮겨주지 않기 때문입니다.
> 보존은 **그 다음 재배포부터** 적용됩니다. 그러니 붙이려면 빠를수록 좋습니다.

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

**PostHog에 이벤트가 하나도 안 들어온다**
→ 배포 URL로 `/api/config`를 열어 `posthog_key`가 채워져 있는지 먼저 보세요.
비어 있으면 환경변수 문제(§5), 채워져 있는데도 안 들어오면 광고 차단기입니다 —
관람객 일부는 원래 안 잡힙니다. §9 참고.

**Sentry에 에러가 안 뜬다**
→ 서버 로그에 `[sentry] 활성화됨`이 있는지 보세요. 없으면 `SENTRY_DSN` 미설정입니다.
401·404·503은 **일부러** 걸러냅니다(정상 동작이라서). 테스트하려면 진짜 500을 내세요.

---

## 9. 운영 도구 — 전시 기간(~9/15) 모니터링

세 가지를 붙였습니다. 셋 다 무료 티어로 충분하고, **환경변수를 비우면 그 도구만
꺼집니다** — 코드를 되돌릴 필요가 없습니다.

| 도구 | 답해주는 질문 | 알림 |
|---|---|---|
| Sentry | 관람객이 어떤 에러를 겪었나 | 이메일 |
| PostHog | 어디서 이탈하나 | 없음(직접 열어봄) |
| UptimeRobot | 서버가 살아 있나 | 이메일/카톡 |

### 9-1. Sentry

sentry.io 가입 → 프로젝트를 **두 개** 만듭니다. Python(FastAPI) 하나, React 하나.
서버 에러와 브라우저 에러는 성격이 완전히 달라서 한 프로젝트에 섞으면 둘 다
읽기 어려워집니다.

각 프로젝트의 DSN을 `SENTRY_DSN`(서버)과 `SENTRY_DSN_FRONTEND`(브라우저)에
넣고 재배포하면 끝입니다.

이미 해둔 것:

- **401·403·404·405·503은 안 보냅니다.** 전부 정상 동작입니다 — 503은 혼잡할 때
  우리가 일부러 거절하는 것이고(§7), 404는 봇 스캔이 하루 수백 건 만듭니다.
  안 걸러내면 전시 첫날 대시보드가 이걸로 덮여 진짜 에러가 묻힙니다
- **관람객 IP·쿠키를 보내지 않습니다**(`send_default_pii=False`)
- **세션 리플레이는 껐습니다.** 관람객 화면을 그대로 녹화하는 기능이라 전시
  앱에서는 개인정보 부담이 큽니다. 화면 흐름은 PostHog로 봅니다
- **분석 실패는 직접 보냅니다.** `try/catch`로 화면에 안내를 띄우고 끝나는 실패는
  Sentry가 자동으로 못 잡는데, 이 앱에서 제일 아픈 실패가 정확히 그 모양입니다

무료 티어는 월 5,000 이벤트입니다. 한 달 전시라면 넉넉하지만, 한 에러가 반복
발생하면 며칠 만에 소진될 수 있습니다 — 그럴 땐 그 에러부터 고치는 게 맞습니다.

### 9-2. PostHog

posthog.com 가입 → 프로젝트 생성 → Project API Key를 `POSTHOG_KEY`에 넣습니다.
가입 시 지역을 EU로 골랐다면 `POSTHOG_HOST=https://eu.i.posthog.com`도 함께.

보내는 이벤트 (`webservice/frontend/src/analytics.ts`의 `EVENTS`):

```
app_opened          앱이 떴다                    ← 퍼널의 분모
  └ guest_started   '체험하기'를 눌렀다
      └ tour_shown  온보딩 안내가 떴다
          └ tour_finished
              └ analyze_started    영상을 올렸다  ← 진짜 첫 경험
                  └ analyze_finished  리포트가 나왔다
                  └ analyze_failed
                      └ live_opened   실시간 화면까지 갔다
```

PostHog에서 **Product analytics → Funnels**로 이 순서대로 넣으면 단계별 이탈률이
나옵니다. 전시 시작 후 3~4일쯤 보는 게 좋습니다 — 첫날 숫자는 지인 트래픽이 섞여
왜곡됩니다.

같이 보면 좋은 것:

- `analyze_finished`의 `seconds` 속성 — 분석 대기가 몇 초부터 이탈로 이어지는지
- `analyze_started`의 `source` — 샘플 영상 vs 직접 올린 영상 비율. 샘플만 쓰면
  업로드 동선에 문제가 있다는 뜻입니다
- `login_failed` — 이게 갑자기 늘면 시드가 안 돌아 데모 계정이 없는 상태입니다(§6)

이미 해둔 것:

- **자동 클릭 수집(autocapture)을 껐습니다.** 이름 없는 이벤트가 수천 개 쌓이면
  무료 한도만 먹고 퍼널은 오히려 읽기 어려워집니다
- **페이지뷰를 직접 보냅니다.** SPA라 주소가 바뀌어도 페이지 로드가 없어서,
  자동 수집에 맡기면 모든 단계가 첫 화면 하나로 뭉쳐 보입니다
- **iframe 안에서는 메모리 저장**으로 내립니다. 서드파티 쿠키·localStorage는
  브라우저가 막거나 접근만 해도 예외를 던집니다(`storage.ts` 주석 참고).
  새로고침마다 새 사람으로 세지지만, 한 방문 안의 퍼널은 그대로 읽힙니다
- **관람객 IP를 저장하지 않습니다**(`ip: false`)
- **SDK를 별도 청크로 분리**했습니다. PostHog+Sentry가 gzip 110KB라 그냥 넣으면
  첫 로딩이 세 배가 됩니다 — 이탈을 재려다 이탈을 만드는 셈입니다. 지금은
  첫 화면 번들이 예전(gzip 75KB)과 같고, 계측은 그 뒤에 따라붙습니다.
  키를 안 넣으면 그 청크는 내려받지도 않습니다

한계를 알고 보세요: 광고 차단기를 쓰는 관람객은 애초에 안 잡힙니다. 절대값이
아니라 **단계 간 비율**로 읽으세요.

### 9-3. UptimeRobot

uptimerobot.com 가입 → Add New Monitor:

| 항목 | 값 |
|---|---|
| Monitor Type | HTTP(s) |
| URL | `https://<배포주소>/api/health` |
| Monitoring Interval | 5 minutes (무료 최소) |
| Alert Contacts | 본인 이메일 |

`/api/health`는 프로세스가 살아 있는지만 보지 않고 **DB를 한 줄 읽어봅니다.**
이 앱의 실제 사고가 '서버는 떠 있는데 DB가 날아가 쓰기만 전부 실패'였기
때문입니다(§6). 실패하면 500을 내므로 UptimeRobot이 알림을 보냅니다.

> 루트 URL(`/`)로 걸지 마세요. SPA 폴백이 무슨 일이 있어도 `index.html`을
> 200으로 돌려주기 때문에, 백엔드가 완전히 망가져도 초록불로 보입니다.

### 9-4. 전시 기간 체크 루틴

**매일 1분** — Sentry 받은편지함에 새 에러가 있는지만 봅니다. 없으면 끝.

**주 1회 5분** — PostHog 퍼널을 열어 이탈이 큰 단계를 하나 고릅니다. 그리고
배포 URL로 `/api/metrics`를 열어 `slow_requests`와 `by_status`의 `503`을 봅니다.
503이 쌓이고 있으면 동시 분석 상한에 계속 걸린다는 뜻이라, 인스턴스를 키우거나
`DAON_MAX_CONCURRENT_JOBS`를 올릴 시점입니다(§7).

**알림이 왔을 때** — UptimeRobot 다운 알림은 대개 재배포·재시작 중이거나
메모리 부족입니다. 플랫폼 로그에서 OOM(`Killed`)부터 확인하세요.
