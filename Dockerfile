# 다온 웹 플랫폼 배포 이미지.
#
#   docker build -t daon .
#   docker run -p 8000:8000 -e DAON_SECRET=... daon
#
# 멀티스테이지인 이유: 프런트 빌드에 필요한 node/npm(수백 MB)과 node_modules 를
# 최종 이미지에 남기지 않기 위해서다. 빌드 결과(dist)만 파이썬 이미지로 옮긴다.

# ---------- 1단계: React 프런트엔드 빌드 ----------
FROM node:20-slim AS frontend

WORKDIR /app/webservice/frontend
# 의존성 파일만 먼저 복사 — 소스만 바뀌었을 때 npm ci 캐시를 재사용한다
COPY webservice/frontend/package.json webservice/frontend/package-lock.json ./
RUN npm ci

COPY webservice/frontend/ ./
RUN npm run build          # → webservice/frontend/dist


# ---------- 2단계: 파이썬 런타임 ----------
FROM python:3.11-slim

# ffmpeg: 아이폰 .mov(HEVC) 업로드를 H.264 로 변환할 때 쓴다. 없으면 그런
#         영상은 분석이 통째로 실패한다.
# libglib2.0-0: opencv-python-headless 가 여전히 요구하는 런타임 라이브러리.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # ultralytics 가 설정·캐시를 쓸 수 있는 경로. 기본값은 홈 디렉터리라
    # 읽기전용 파일시스템에서 기동이 실패한다.
    YOLO_CONFIG_DIR=/app/.ultralytics \
    MPLCONFIGDIR=/tmp/mpl

COPY requirements.txt ./
# CPU 전용 torch wheel. 기본 PyPI 의 torch 는 CUDA 런타임을 포함해 2GB가 넘고
# 저가 인스턴스의 디스크 한도를 넘긴다.
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

# webservice/ 에 더해, live_self.py(셀프캠 체험)가 임포트하는 루트 모듈들을
# 함께 복사한다. 예전에는 "webservice 는 루트 모듈을 임포트하지 않는다"가
# 맞았지만 v6 서빙 통합 때부터 아니다 — 이 목록이 빠지면 컨테이너가
# `ModuleNotFoundError: tiles` 로 기동조차 못 한다(실제 배포 사고).
# main.py·pose_source.py 등 나머지 루트 모듈은 여전히 넣지 않는다. 서버에
# 없는 의존성(pyserial, mediapipe)을 요구하는 코드를 이미지에 남기지 않기 위해서다.
COPY webservice/ ./webservice/
COPY tiles.py numpy_compat.py config.py temporal_risk.py profiles.json ./
# 낙상 위험 모델. .dockerignore 의 *.joblib 제외에서 이 파일만 되살려 놓았다.
# 없으면 서버는 뜨지만 셀프캠 체험이 '모델 파일 없음'으로 조용히 꺼진다.
COPY fall_risk_model_v5.joblib ./
# 프런트 빌드 산출물을 1단계에서 가져온다
COPY --from=frontend /app/webservice/frontend/dist ./webservice/frontend/dist

# YOLO 가중치를 빌드 시점에 받아둔다. 런타임에 받으면 첫 사용자가 다운로드를
# 기다리게 되고, 네트워크가 막힌 환경에서는 아예 실패한다.
RUN mkdir -p /app/.ultralytics && \
    python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')" && \
    ls -la yolo11n.pt

# 업로드·리포트 저장 경로. 볼륨을 안 붙이면 재시작 시 사라진다(가이드 참고).
# samples/ 는 사전 계산된 캐시라 저장소에서 그대로 복사돼 온다(비어 있어도 무방).
RUN mkdir -p webservice/consulting/uploads webservice/consulting/reports \
             webservice/consulting/samples

EXPOSE 8000
ENV PORT=8000

# 데모 계정을 시드한 뒤 서버를 띄운다. seed 는 멱등이라 재시작해도 안전하다.
CMD ["sh", "-c", "python -m webservice.seed && exec uvicorn webservice.app:app --host 0.0.0.0 --port ${PORT}"]
