# Flask + HTMX + Alpine.js 프로젝트 스켈레톤

새로운 웹 프로젝트를 빠르게 시작하기 위한 경량 스켈레톤입니다. Flask(백엔드), HTMX(서버 인터랙션), Alpine.js(클라이언트 인터랙션)가 미리 설정되어 있어 바로 개발을 시작할 수 있습니다.

## 🎯 이 스켈레톤의 목적

이 프로젝트는 **실제 애플리케이션이 아니라**, 새로운 프로젝트를 시작할 때 사용할 수 있는 **기반 템플릿**입니다. 

- ✅ Flask 앱 구조가 미리 설정되어 있음
- ✅ HTMX와 Alpine.js가 통합되어 있음
- ✅ SQLite 데이터베이스 연결 및 초기화 기능 포함
- ✅ 예제 코드로 각 기술의 사용법을 확인할 수 있음
- ✅ 필요에 따라 예제 코드를 삭제하고 본인의 기능으로 교체 가능

## 📋 목차

- [기술 스택](#기술-스택)
- [빠른 시작](#빠른-시작)
- [프로젝트 구조](#프로젝트-구조)
- [사용 방법](#사용-방법)
- [개발 가이드](#개발-가이드)

## 🛠 기술 스택

- **Backend**: Flask (Python)
- **Frontend Interaction**: HTMX (AJAX 대체, HTML 조각 교환)
- **Frontend Logic**: Alpine.js (경량 Vue/React 대체)
- **Database**: SQLite
- **Styling**: Tailwind CSS (CDN)

## 🚀 빠른 시작

### 1. 프로젝트 복사

이 스켈레톤을 새 프로젝트 디렉토리로 복사하거나 클론합니다.

### 2. 가상환경 생성 및 활성화

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 데이터베이스 초기화 (필요한 경우)

```bash
flask init-db
```

### 5. 서버 실행

```bash
python run.py
```

브라우저에서 `http://127.0.0.1:5000` 접속하여 예제를 확인할 수 있습니다.

## 📁 프로젝트 구조

```
new_project/
├── app/
│   ├── __init__.py           # Flask 앱 팩토리 (앱 초기화)
│   ├── db.py                 # 데이터베이스 연결 및 초기화 유틸리티
│   ├── routes.py             # 라우트 정의 (예제 라우트 포함)
│   ├── schema.sql            # 데이터베이스 스키마 (예제 테이블)
│   ├── static/               # 정적 파일 (CSS, JS, 이미지)
│   └── templates/            # HTML 템플릿
│       ├── base.html         # 기본 레이아웃 (HTMX, Alpine.js 로드)
│       ├── index.html        # 메인 페이지 (예제 포함)
│       └── partials/         # HTMX용 HTML 조각 (예제 Partial)
│           ├── time.html
│           └── todo_list.html
├── database.db               # SQLite 데이터베이스 파일 (자동 생성)
├── run.py                    # 애플리케이션 실행 엔트리포인트
├── requirements.txt          # Python 의존성 목록
└── README.md                 # 프로젝트 문서
```

## 💡 사용 방법

### 1. 프로젝트 이름 변경

프로젝트를 복사한 후, 다음을 수정하세요:
- 디렉토리 이름
- `app/__init__.py`의 앱 설정
- `base.html`의 타이틀 및 메타 정보

### 2. 예제 코드 제거 또는 수정

현재 포함된 예제 코드들:
- **Todo 관리 예제** (`routes.py`의 Todo 관련 라우트, `todo_list.html`)
- **Alpine.js 예제** (`index.html`의 카운터 및 토글)
- **서버 시간 예제** (`routes.py`의 `/time` 라우트, `time.html`)

이 예제들은 각 기술의 사용법을 보여주는 데모입니다. 본인의 프로젝트에 맞게 수정하거나 삭제하세요.

### 3. 데이터베이스 스키마 수정

`app/schema.sql` 파일을 수정하여 본인의 데이터베이스 스키마를 정의하세요.

## 📚 개발 가이드

### 새로운 라우트 추가

`app/routes.py`에 새로운 라우트를 추가합니다:

```python
@main.route('/your-route')
def your_handler():
    # 로직 구현
    return render_template('your_template.html', data=data)
```

### HTMX 사용하기

HTMX는 HTML 속성을 통해 서버와 통신합니다:

```html
<!-- GET 요청 예제 -->
<button hx-get="/api/data" hx-target="#result">데이터 가져오기</button>
<div id="result"></div>

<!-- POST 요청 예제 -->
<form hx-post="/api/submit" hx-target="#result">
    <input name="data" />
    <button type="submit">제출</button>
</form>
```

주요 HTMX 속성:
- `hx-get`, `hx-post`, `hx-put`, `hx-delete` - HTTP 메서드 지정
- `hx-target` - 응답을 삽입할 대상 요소 (CSS 선택자)
- `hx-swap` - 삽입 방식 (`innerHTML`, `outerHTML`, `beforebegin`, `afterend` 등)
- `hx-confirm` - 확인 대화상자 표시
- `hx-on::after-request` - 요청 후 실행할 JavaScript

### Alpine.js 사용하기

Alpine.js는 경량 JavaScript 프레임워크로 클라이언트 상태를 관리합니다:

```html
<div x-data="{ count: 0, isOpen: false }">
    <p x-text="count"></p>
    <button @click="count++">증가</button>
    <button @click="isOpen = !isOpen">토글</button>
    <div x-show="isOpen" x-transition>내용</div>
</div>
```

주요 Alpine.js 지시어:
- `x-data` - 컴포넌트 상태 선언
- `x-text`, `x-html` - 텍스트/HTML 바인딩
- `@click`, `@input`, `@submit` - 이벤트 핸들러
- `x-show`, `x-if` - 조건부 렌더링
- `x-for` - 리스트 렌더링
- `x-transition` - 전환 효과

### Partial 템플릿 사용

HTMX와 함께 사용할 HTML 조각은 `app/templates/partials/` 디렉토리에 저장합니다:

```python
# routes.py
@main.route('/api/data')
def get_data():
    data = fetch_data()
    return render_template('partials/data.html', data=data)
```

### 데이터베이스 작업

`app/db.py`의 `get_db()` 함수를 사용하여 데이터베이스 연결을 가져옵니다:

```python
from app.db import get_db

db = get_db()

# 조회
results = db.execute('SELECT * FROM table_name').fetchall()

# 단일 행 조회
result = db.execute('SELECT * FROM table_name WHERE id = ?', [id]).fetchone()

# 삽입
db.execute('INSERT INTO table_name (column) VALUES (?)', [value])
db.commit()

# 업데이트
db.execute('UPDATE table_name SET column = ? WHERE id = ?', [value, id])
db.commit()

# 삭제
db.execute('DELETE FROM table_name WHERE id = ?', [id])
db.commit()
```

### 정적 파일 사용

CSS, JavaScript, 이미지 파일은 `app/static/` 디렉토리에 저장하고, 템플릿에서 다음과 같이 참조합니다:

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
<script src="{{ url_for('static', filename='js/script.js') }}"></script>
<img src="{{ url_for('static', filename='images/logo.png') }}" alt="Logo">
```

## 📝 참고 자료

- [Flask 공식 문서](https://flask.palletsprojects.com/)
- [HTMX 공식 문서](https://htmx.org/)
- [Alpine.js 공식 문서](https://alpinejs.dev/)
- [Tailwind CSS 공식 문서](https://tailwindcss.com/)

## 🔄 다음 단계

1. 예제 코드를 본인의 기능으로 교체
2. 데이터베이스 스키마 수정
3. 필요한 추가 라이브러리 설치 및 설정
4. 프로덕션 환경 설정 (환경 변수, 보안 설정 등)

## 📄 라이선스

이 스켈레톤은 학습 및 개발 목적으로 자유롭게 사용할 수 있습니다.
