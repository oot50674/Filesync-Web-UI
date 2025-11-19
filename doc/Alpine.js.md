## 1. Alpine.js 한 줄 요약

* **역할**
  Vue/React처럼 **반응형 상태 + 템플릿 바인딩**을 제공하는데,
  컴포넌트 파일을 따로 만들지 않고 **HTML에 `x-*` 속성만 뿌려서 쓰는 경량 라이브러리**에요.([daily.dev][1])

* **언제 쓰기 좋은지**

  * 서버 렌더(SSR) + HTMX 구조에서
  * “모달 토글, 드롭다운, 탭, 간단한 폼 검증, 입력 미러링”처럼
    **서버 왕복까지 할 필요 없는 자잘한 인터랙션** 담당용으로 잘 어울려요.([daily.dev][1])

---

## 2. 설치 – 제일 간단한 CDN 방식

HTML `<head>`에 스크립트 한 줄만 추가하면 돼요:

```html
<script
  defer
  src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"
></script>
```

`defer`는 DOM 파싱 끝난 뒤에 Alpine을 실행하게 하는 플래그라, 기본 예제에서도 이렇게 붙여서 쓰는 걸 권장하거든요.([itf-laravel-11.netlify.app][2])

번들러(Vite, Webpack 등)를 쓰면 ESM으로도 쓸 수 있지만, 처음에는 CDN 쓰는 게 제일 편해요.

---

## 3. 첫 컴포넌트: 카운터 예제로 감 잡기

Alpine의 기본 단위는 `x-data`가 붙은 “컴포넌트 스코프”에요.([Alpine.js][3])

```html
<div x-data="{ count: 0 }">
  <button @click="count++">증가</button>
  <span x-text="count"></span>
</div>
```

여기서 일어나는 일:

* `x-data="{ count: 0 }"`
  → 이 `div`를 Alpine 컴포넌트로 만들고, `count`라는 반응형 상태를 선언해요.([Alpine.js][3])
* `@click="count++"` (`x-on:click`의 축약형)
  → 버튼 클릭 시 `count` 값을 증가시키는 이벤트 핸들러에요.([Alpine.js][4])
* `x-text="count"`
  → `span` 안의 텍스트를 항상 `count` 값과 동기화해요.([Alpine.js][5])

이 세 줄만으로 “상태 → UI → 이벤트 → 상태 업데이트” 루프가 완성됩니다.

---

## 4. 꼭 알아두면 되는 핵심 디렉티브 6개

### 4-1. `x-data` – 컴포넌트와 상태 정의

```html
<div x-data="{ open: false, toggle() { this.open = !this.open } }">
  <button @click="toggle()">Toggle</button>
  <div x-show="open">내용</div>
</div>
```

* 이 `div`와 하위 요소들이 **하나의 Alpine 컴포넌트**가 돼요.
* 객체 안에 **상태(`open`)와 메서드(`toggle`)**를 같이 넣을 수 있어요.([Alpine.js][3])

---

### 4-2. `x-text` – 텍스트 바인딩

```html
<div x-data="{ msg: 'Hello' }">
  <span x-text="msg"></span>
</div>
```

* Vue의 `{{ msg }}` 같은 느낌으로,
  요소의 텍스트 내용을 JS 표현식 결과로 채워줘요.([Alpine.js][5])

---

### 4-3. `x-on` / `@` – 이벤트 리스너

```html
<button x-data @click="alert('Hello Alpine!')">
  클릭
</button>
```

* `x-on:click="..."`의 축약형이 `@click="..."` 에요.([Alpine.js][4])
* `$event` 매직 프로퍼티로 원래 이벤트 객체에 접근할 수도 있어요.([Alpine.js][4])

---

### 4-4. `x-show` – 요소 show/hide (CSS 기반)

```html
<div x-data="{ open: false }">
  <button @click="open = !open">토글</button>
  <div x-show="open">보이거나 숨겨질 내용</div>
</div>
```

* 조건이 `true`면 보여주고, `false`면 `display: none`으로 숨겨요.([Alpine.js][6])
* `x-transition`을 같이 쓰면 자연스러운 등장/퇴장 애니메이션도 바로 붙일 수 있어요.([Alpine.js][6])

---

### 4-5. `x-model` – 입력과 상태의 양방향 바인딩

```html
<div x-data="{ message: '' }">
  <input type="text" x-model="message" />
  <p x-text="message"></p>
</div>
```

* 인풋 값 ↔ 데이터 속성 사이를 **자동으로 동기화**해줘요.([Alpine.js][7])
* `.lazy`, `.debounce`, `.throttle`, `.number` 같은 모디파이어로
  업데이트 타이밍이나 타입을 조절할 수 있어요.([Alpine.js][7])

---

### 4-6. `x-bind` / `:` – 속성 바인딩

```html
<div x-data="{ active: true }">
  <button
    :class="active ? 'btn btn-primary' : 'btn btn-outline'"
    :disabled="!active"
  >
    버튼
  </button>
</div>
```

* `x-bind:class="..."`의 축약형이 `:class`,
  `x-bind:disabled="..."`의 축약형이 `:disabled` 이런 식이에요.([Alpine.js][8])

---

## 5. 한 단계 더: 자주 쓰이는 보조 기능

### 5-1. `x-init` – 초기화 코드 실행

```html
<div
  x-data="{ loaded: false }"
  x-init="setTimeout(() => loaded = true, 500)"
>
  <span x-show="!loaded">로딩 중...</span>
  <span x-show="loaded">완료!</span>
</div>
```

* 컴포넌트가 DOM에 붙을 때 한 번 실행되는 초기화 훅입니다.([Medium][9])

---

### 5-2. `x-for` – 반복 렌더링

```html
<div x-data="{ todos: ['a', 'b', 'c'] }">
  <template x-for="todo in todos" :key="todo">
    <li x-text="todo"></li>
  </template>
</div>
```

* 리스트 렌더링용 디렉티브에요.
* `template` 태그 안의 내용을 반복해서 DOM으로 풀어줍니다.([daily.dev][1])

---

### 5-3. `x-transition` – `x-show`와 함께 쓰는 트랜지션

```html
<div x-data="{ open: false }">
  <button @click="open = !open">토글</button>

  <div x-show="open" x-transition>
    부드럽게 나왔다 들어가는 블록
  </div>
</div>
```

* `x-show`로 보이고/숨겨질 때 CSS transition을 자동으로 붙여줘요.([Alpine.js][6])

---

## 6. HTMX + Alpine.js 같이 쓸 때 그림

둘의 역할을 이렇게 나눠서 생각하면 편해요:

* **HTMX**

  * 서버에 HTTP 요청 보내서 **HTML 조각을 가져오고 교체**하는 역할
  * 목록 갱신, 페이지네이션, 서버 필터링, 폼 제출 등
* **Alpine.js**

  * 그 HTML 조각 안에서, **브라우저 로컬 상태와 인터랙션** 담당
  * 드롭다운, 모달, 탭, 입력값 미러링, 간단한 유효성 검사 등

Laravel Livewire 같은 서버 렌더링 스택에서도
“서버 컴포넌트 + Alpine.js로 클라이언트 인터랙션” 조합을 공식적으로 추천하는 패턴이라, HTMX와 묶어서 써도 비슷한 감각으로 운용할 수 있어요.([Livewire][10])

---

## 7. 요약

* Alpine.js는 **Vue/React식 반응형 모델을 “HTML 속성 몇 개”로 가져다 쓰는 라이브러리**에요.([daily.dev][1])
* `x-data`, `x-text`, `x-on(@)`, `x-show`, `x-model`, `x-bind(:)`
  이 6개만 알아도 웬만한 인터랙션은 다 처리할 수 있어요.
* HTMX로 서버에서 HTML 조각 가져오고,
  그 조각 안에서 Alpine으로 로컬 상태/동작을 붙이는 식으로 같이 쓰면 꽤 깔끔하게 구조가 나옵니다.

[1]: https://daily.dev/blog/alpine-js-the-ultimate-guide?utm_source=chatgpt.com "Getting Started with Alpine.js - The Ultimate Guide"
[2]: https://itf-laravel-11.netlify.app/concepts/alpine?utm_source=chatgpt.com "Core Concepts - Alpine.js"
[3]: https://alpinejs.dev/directives/data?utm_source=chatgpt.com "x-data"
[4]: https://alpinejs.dev/directives/on?utm_source=chatgpt.com "x-on"
[5]: https://alpinejs.dev/start-here?utm_source=chatgpt.com "Start Here"
[6]: https://alpinejs.dev/directives/show?utm_source=chatgpt.com "x-show"
[7]: https://alpinejs.dev/directives/model?utm_source=chatgpt.com "x-model"
[8]: https://alpinejs.dev/directives/bind?utm_source=chatgpt.com "x-bind"
[9]: https://zubairidrisaweda.medium.com/getting-started-with-alpine-js-f6203becf717?utm_source=chatgpt.com "Getting Started With Alpine.js"
[10]: https://laravel-livewire.com/docs/2.x/alpine-js?utm_source=chatgpt.com "AlpineJS"
