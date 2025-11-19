# Filesync Web UI

**Filesync Web UI**는 로컬 파일 동기화 작업을 관리하고 모니터링하기 위한 웹 기반 인터페이스입니다.  
Python과 Flask로 구축되었으며, HTMX를 사용하여 페이지 새로고침 없이 실시간으로 동기화 상태를 확인할 수 있습니다.

## ✨ 주요 기능

- **동기화 설정 관리**:
  - 원본(Source) 및 대상(Replica) 폴더 경로 설정
  - 파일명 패턴 필터링 (예: `*.log`, `backup_*`)
  - 스캔 간격 및 파일 보존 기간(Retention Days) 설정
- **동기화 제어**: 웹 인터페이스에서 동기화 프로세스를 시작하거나 중지할 수 있습니다.
- **실시간 상태 모니터링**:
  - 현재 처리 중인 파일, 진행률, 상태(IDLE, SCANNING, COPYING 등)를 실시간으로 표시합니다.
  - HTMX 폴링을 통해 서버 부하를 최소화하며 UI를 업데이트합니다.
- **안정화 대기(Settle Time)**: 파일 복사 전 파일 크기/수정 시간이 안정화될 때까지 대기하여 불완전한 복사를 방지합니다.
- **자동 정리**: 설정된 보존 기간이 지난 백업 파일을 대상 폴더에서 자동으로 삭제합니다.

## 🛠 기술 스택

- **Backend**: Python 3, Flask
- **Frontend**: HTML5, HTMX, Alpine.js, Tailwind CSS (Inline/Utility classes)
- **Database**: SQLite
- **Process Management**: Python `threading`을 이용한 백그라운드 동기화 프로세스 관리

## 🚀 설치 및 실행 방법

### 1. 환경 설정

프로젝트 루트 디렉토리에서 가상 환경을 생성하고 활성화합니다.

```bash
# 가상 환경 생성
python -m venv venv

# 가상 환경 활성화 (Windows)
venv\Scripts\activate

# 가상 환경 활성화 (macOS/Linux)
source venv/bin/activate
```

### 2. 의존성 설치

필요한 Python 패키지를 설치합니다.

```bash
pip install -r requirements.txt
```

### 3. 데이터베이스 초기화

최초 실행 전 또는 스키마 변경 시 데이터베이스를 초기화합니다.

```bash
flask init-db
```

### 4. 서버 실행

개발 서버를 실행합니다.

```bash
python run.py
```

서버가 시작되면 브라우저에서 `http://127.0.0.1:5120`으로 접속하여 사용할 수 있습니다.

## 📂 프로젝트 구조

```
Filesync-Web-UI/
├── app/
│   ├── __init__.py      # Flask 앱 팩토리 및 설정
│   ├── db.py            # SQLite 데이터베이스 연결 관리
│   ├── filesync.py      # 파일 동기화 핵심 로직 (Watcher, Copier)
│   ├── routes.py        # 웹 라우트 및 HTMX 엔드포인트
│   ├── schema.sql       # 데이터베이스 스키마 (sync_configs)
│   ├── static/          # 정적 파일 (CSS, JS)
│   └── templates/       # Jinja2 템플릿
│       ├── base.html    # 기본 레이아웃
│       ├── index.html   # 메인 페이지
│       └── partials/    # HTMX용 HTML 조각 (설정 폼, 상태 표시)
├── doc/                 # 문서 (HTMX, Alpine.js 가이드 등)
├── run.py               # 애플리케이션 진입점
├── requirements.txt     # 의존성 목록
└── README.md            # 프로젝트 설명서
```

## 📝 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

