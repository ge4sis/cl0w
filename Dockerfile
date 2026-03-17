FROM python:3.12-slim

WORKDIR /app

# non-root 사용자 생성
RUN useradd -m -u 1000 cl0w

# 의존성 먼저 설치 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 복사
COPY --chown=cl0w:cl0w . .

# writable 디렉터리 초기화 (volume mount 전 소유권 확보)
RUN mkdir -p sessions tools && chown cl0w:cl0w sessions tools

USER cl0w

CMD ["python", "bot.py"]
