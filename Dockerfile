# Python 3.13 슬림 이미지 사용
FROM python:3.13-slim

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 환경 변수 설정
ENV FLASK_APP=app
ENV PYTHONUNBUFFERED=1

# 포트 노출
EXPOSE 5120

# 서버 실행 (모든 IP에서 접근 가능하도록 설정)
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=5120"]

