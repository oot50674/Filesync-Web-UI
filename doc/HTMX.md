HTMX를 처음 쓰는 입장에서 “어디까지 알아야 쓸 수 있지?” 기준으로 정리해볼게요.
(예제는 전부 **서버에서 HTML 조각을 돌려준다**는 기본 철학을 전제로 합니다.)

---

## 1. HTMX 한 줄 요약

* **뭐냐?**
  HTML 태그에 `hx-*` 속성을 붙여서 **AJAX / CSS 전환 / SSE / WebSocket** 같은 걸 직접 제어하게 해주는 JS 라이브러리입니다.([htmx.org][1])
* **철학**
  “JSON + SPA 프레임워크” 대신, **서버에서 HTML을 렌더링 → 부분 교체**만으로 동적 UI를 만들자는 쪽입니다.([위키백과][2])
* **특징**

  * 의존성 없음, 작은 용량 (~14~16kB gzipped)([htmx.org][1])
  * 대부분의 로직/상태를 **백엔드에 두고**, 프론트는 그냥 “하이퍼텍스트”에 가깝게 유지

---

## 2. 설치 – 제일 간단한 방식

HTML 템플릿에 스크립트 하나만 추가하면 됩니다.

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>htmx 예제</title>
    <script src="https://unpkg.com/htmx.org@2.0.6"></script>
  </head>
  <body>
    ...
  </body>
</html>
```

버전은 공식 문서/리포지토리에서 최신으로 맞추면 됩니다.([htmx.org][3])

---

## 3. 핵심 개념 – “요청 + 응답 조각 교체”

HTMX의 기본 동작은 딱 하나입니다:

> 어떤 이벤트가 발생하면 → 서버로 HTTP 요청을 보내고 → 돌아온 HTML 조각을 DOM의 특정 위치에 교체/삽입한다.([htmx.org][3])

이를 위해 몇 개의 필수 속성만 알면 됩니다.

| 속성           | 역할                                         |
| ------------ | ------------------------------------------ |
| `hx-get`     | GET 요청 보냄                                  |
| `hx-post`    | POST 요청 보냄                                 |
| `hx-put`     | PUT 요청                                     |
| `hx-delete`  | DELETE 요청                                  |
| `hx-target`  | 응답 HTML을 꽂아 넣을 대상 선택자 지정                   |
| `hx-swap`    | 응답을 어떻게 꽂을지 전략 지정 (innerHTML, outerHTML 등) |
| `hx-trigger` | 어떤 이벤트에 요청을 보낼지 지정                         |

이 정도만 익혀도 웬만한 CRUD 화면은 전부 만들 수 있습니다.([htmx.org][3])

---

## 4. 가장 단순한 예제 – 버튼 클릭으로 영역 교체

### 4-1. HTML

```html
<div id="counter-area">
  <p>현재 값: 0</p>
  <button
    hx-post="/counter/increase"
    hx-target="#counter-area"
    hx-swap="outerHTML"
  >
    +1
  </button>
</div>
```

설명:

* 버튼을 누르면 `/counter/increase`로 **POST 요청**을 보냅니다.
* 서버는 `#counter-area` 전체를 새 HTML로 렌더링해서 돌려줍니다.
* `hx-target="#counter-area"`: 응답을 이 div에 적용
* `hx-swap="outerHTML"`: div 자체를 통째로 갈아끼웁니다.([htmx.org][3])

### 4-2. 서버 (예: Flask 느낌의 의사 코드)

```python
@app.post("/counter/increase")
def counter_increase():
    value = get_from_db() + 1
    save_to_db(value)
    return render_template("counter_fragment.html", value=value)
```

`counter_fragment.html`은 이렇게 생겼다고 가정합니다:

```html
<div id="counter-area">
  <p>현재 값: {{ value }}</p>
  <button
    hx-post="/counter/increase"
    hx-target="#counter-area"
    hx-swap="outerHTML"
  >
    +1
  </button>
</div>
```

이런 식으로 **프래그먼트 템플릿**을 만들어 두고 계속 돌려쓰는 패턴이 기본입니다.

---

## 5. 자주 쓰는 속성들 정리

### 5-1. `hx-get`, `hx-post` + `hx-target`, `hx-swap`

```html
<ul id="todo-list">
  <!-- 기존 항목들 -->
</ul>

<button
  hx-get="/todos/new-form"
  hx-target="#todo-list"
  hx-swap="beforeend"
>
  새 할 일 추가
</button>
```

* 응답으로 `<li>...</li>` 같은 HTML 조각이 온다고 가정하면,
* `hx-swap="beforeend"` 때문에 `<ul>`의 맨 끝에 항목이 추가됩니다.([htmx.org][3])

대표적인 `hx-swap` 옵션:

* `innerHTML`(기본값) : target 안을 전부 바꿈
* `outerHTML` : target 자신을 통째로 바꿈
* `beforebegin` / `afterbegin` / `beforeend` / `afterend` : DOM 삽입 위치 지정
* `delete` : 삭제, `none` : 아무것도 하지 않음 (응답만 소비)

### 5-2. `hx-trigger`

기본 이벤트 말고 다른 트리거로도 요청을 보낼 수 있습니다.([htmx.org][3])

```html
<input
  type="text"
  name="keyword"
  placeholder="검색어"
  hx-get="/search"
  hx-target="#result"
  hx-trigger="keyup changed delay:300ms"
/>

<div id="result"></div>
```

* `keyup changed delay:300ms`

  * 키를 입력해서 값이 바뀌면
  * 300ms 동안 추가 입력이 없을 때 요청

디바운스 검색 같은 UX를 HTML 속성만으로 만들 수 있습니다.

### 5-3. 폼과 함께 쓰기

```html
<form
  hx-post="/todos"
  hx-target="#todo-list"
  hx-swap="beforeend"
>
  <input type="text" name="title" required />
  <button type="submit">추가</button>
</form>

<ul id="todo-list">...</ul>
```

* 폼이 submit 되면 `/todos`로 POST
* 서버는 `<li>새로운 항목</li>`만 돌려주고
* HTMX가 `#todo-list`의 끝에 붙입니다.

기본적인 서버–렌더링 방식 그대로인데, **페이지 전체 새로고침만 없앤다**고 생각하면 이해가 편합니다.([xlwings][4])

---

## 6. URL/히스토리 다루기 – `hx-push-url`, `hx-boost`

SPA처럼 브라우저 뒤로 가기도 어느 정도 처리할 수 있습니다.

### 6-1. `hx-push-url`

```html
<div
  id="content"
  hx-get="/page/1"
  hx-push-url="true"
  hx-target="#content"
  hx-swap="innerHTML"
>
  첫 페이지 로딩 중...
</div>
```

* 응답을 교체할 때 **현재 URL도 함께 변경**해서 히스토리에 남깁니다.([htmx.org][5])

### 6-2. `hx-boost`

기존 `<a>`, `<form>`을 **자동으로 AJAX 링크/폼**처럼 동작하게 만들 수 있습니다.

```html
<body hx-boost="true">
  <a href="/articles/1">글 1</a>
  <a href="/articles/2">글 2</a>
</body>
```

* 링크를 클릭하면 전체 페이지 새로고침 대신 **부분 로드 + 히스토리 갱신** 방식으로 변합니다.([htmx.org][5])

---

## 7. 로딩 상태 / 에러 처리

### 7-1. 로딩 인디케이터 – `hx-indicator`

```html
<button
  hx-get="/slow-api"
  hx-target="#result"
  hx-indicator="#spinner"
>
  불러오기
</button>

<div id="spinner" class="htmx-indicator">로딩 중...</div>
<div id="result"></div>
```

* 요청 동안 `#spinner`에 `.htmx-indicator` 클래스를 자동으로 붙였다 떼줍니다.([htmx.org][5])

CSS (예):

```css
.htmx-indicator {
  display: none;
}

.htmx-request .htmx-indicator {
  display: inline-block;
}
```

### 7-2. 에러 처리 – HTTP 코드 활용

* 4xx, 5xx 같은 에러 응답을 보내면 HTMX가 기본적으로는 아무것도 교체하지 않습니다.
* `hx-target`을 에러 영역으로 지정하거나,
  `htmx:responseError` 이벤트에 리스너를 달아서 JS로 토스트/알림을 띄우는 패턴도 있습니다.([htmx.org][5])

---

## 8. 백엔드 템플릿 구조 – 추천 패턴

대부분의 서버 프레임워크(Django, Flask, Rails, Spring 등)는 HTMX와 잘 붙습니다.([위키백과][2])

보통 이런 구조로 나누면 관리가 편합니다.

* `base.html` – 레이아웃/헤더/푸터
* `page_todos.html` – 전체 페이지 (일반 브라우저 요청에 사용)
* `fragments/_todo_item.html` – `<li>` 하나
* `fragments/_todo_list.html` – `<ul>` 전체

라우트 설계 예:

* `GET /todos` → 전체 페이지 (`page_todos.html`)
* `POST /todos` → 새 `<li>`만 응답 (`_todo_item.html`)
* `GET /todos/list-fragment` → 전체 `<ul>`만 응답 (`_todo_list.html`)

“같은 데이터인데, 전체 페이지 vs 프래그먼트 템플릿을 나눠서 렌더링한다”는 관점을 유지하면 설계가 깔끔해집니다.

---

## 9. HTMX를 쓸 때의 마인드셋 요약

* **상태는 최대한 서버에 둔다.**
* 클라이언트는 “HTML 하이퍼텍스트 + 약간의 JS” 수준에 머물게 한다.
* **JSON API + 거대한 JS 프레임워크**를 쓰기 전에
  “그냥 HTML 조각 몇 개만 왔다 갔다 하면 되지 않나?”를 먼저 생각해 보는 용도라고 보면 편합니다.([위키백과][2])

---

## 10. 다음 단계로 보면 좋은 것들

필요하면 이런 키워드를 문서에서 보면 좋습니다.

* `hx-vals`, `hx-include`로 추가 데이터 보내기
* 서버 이벤트(SSE)용 `hx-sse`, WebSocket 관련 확장
* `htmx.on("htmx:afterSwap", ...)` 같은 이벤트 훅
* CSRF 토큰, 인증 쿠키와의 연동

공식 문서의 “Docs → AJAX / Attributes / Events / Examples” 섹션을 한 번씩 쭉 훑어 보면 전체 그림이 잡힙니다.([htmx.org][3])

---


[1]: https://htmx.org/?utm_source=chatgpt.com "</> htmx - high power tools for html"
[2]: https://en.wikipedia.org/wiki/Htmx?utm_source=chatgpt.com "Htmx"
[3]: https://htmx.org/docs/?utm_source=chatgpt.com "</> htmx ~ Documentation"
[4]: https://server.xlwings.org/en/latest/htmx/?utm_source=chatgpt.com "htmx - xlwings Server documentation"
[5]: https://htmx.org/reference/?utm_source=chatgpt.com "Reference"