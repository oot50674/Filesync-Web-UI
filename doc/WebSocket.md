# Alpine.js 및 WebSocket 구현 명세

이 문서는 `Filesync-Web-UI` 프로젝트에서 사용된 Alpine.js 기반의 프론트엔드 반응형 로직과 Flask-SocketIO를 이용한 실시간 통신 구현 내용을 정리합니다.

## 1. 개요

시스템은 파일 동기화 작업의 **실시간 상태 진행률**을 사용자에게 보여주기 위해 WebSocket을 사용하며, **UI 상태 관리 및 업데이트**를 위해 Alpine.js를 사용합니다.

- **Backend**: Flask, Flask-SocketIO (threading 모드)
- **Frontend**: Alpine.js v3, Socket.IO Client v4
- **Communication**:
  - **상태 수신 (Server → Client)**: WebSocket (`sync_update` 이벤트)
  - **명령 전송 (Client → Server)**: HTTP POST (Fetch API)

---

## 2. 서버 측 구현 (Server-Side)

서버는 동기화 작업의 상태가 변경될 때마다 WebSocket 이벤트를 브로드캐스트합니다.

### 2.1 초기화 (`app/__init__.py`)
Flask 애플리케이션 팩토리 패턴 내에서 SocketIO를 초기화합니다.

```python
from flask_socketio import SocketIO

# 비동기 모드를 threading으로 설정 (Windows 호환성 및 간단한 구조 위함)
socketio = SocketIO(async_mode='threading')

def create_app():
    app = Flask(__name__)
    # ...
    socketio.init_app(app, async_mode='threading')
    return app
```

### 2.2 이벤트 발송 (`app/routes.py`)
동기화 매니저나 작업 처리 로직에서 상태 변화가 감지되면 `_emit_status_event` 함수를 통해 클라이언트로 데이터를 전송합니다.

```python
def _emit_status_event(config_id, is_running, status):
    try:
        # 'sync_update' 채널로 상태 데이터 브로드캐스트
        socketio.emit("sync_update", {
            "config_id": config_id,
            "is_running": is_running,
            "status": status,  # { state, details, current_file, progress_percent, updated_at }
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception:
        logger.exception("Failed to emit sync_update")
```

---

## 3. 클라이언트 측 구현 (Client-Side)

클라이언트는 전역 헬퍼 함수를 통해 소켓 연결을 관리하며, Alpine.js 컴포넌트가 이를 구독하여 UI를 갱신합니다.

### 3.1 소켓 연결 관리 (`app/static/js/scripts.js`)
`FileSyncApp` 전역 객체 내에 싱글톤 패턴으로 소켓 연결을 관리합니다. 페이지 내 여러 컴포넌트가 있어도 소켓 연결은 하나만 유지됩니다.

```javascript
const getSyncSocket = () => {
    if (socketInstance) return socketInstance;
    
    // Socket.IO 클라이언트 초기화
    socketInstance = window.io({
        path: resolveUrl('/socket.io'), // 서브 디렉토리 배포 고려
    });
    return socketInstance;
};
```

### 3.2 Alpine.js 컴포넌트: `syncStatusPanel`
동기화 카드의 상태를 관리하는 핵심 컴포넌트입니다. WebSocket 이벤트를 수신하여 프로그레스 바와 상태 텍스트를 실시간으로 업데이트합니다.

#### 주요 로직
1.  **`init()`**: 컴포넌트 로드 시 `bindSocket()`을 호출합니다.
2.  **`bindSocket()`**: `sync_update` 이벤트를 구독하고, 메시지의 `config_id`가 자신의 ID와 일치할 때만 상태를 반영합니다.
3.  **`applyStatus()`**: 수신된 JSON 데이터를 기반으로 `isRunning`, `progressPercent`, `details` 등의 반응형 변수를 갱신합니다.

```javascript
window.syncStatusPanel = (options) => {
    return {
        configId: options.configId,
        isRunning: false,
        progressPercent: 0,
        // ... 변수들

        init() {
            this.bindSocket();
        },

        bindSocket() {
            const socket = app.getSyncSocket();
            // 서버로부터 'sync_update' 이벤트 수신
            socket.on('sync_update', (payload) => {
                // 내 카드의 설정 ID와 일치하는지 확인
                if (!payload || payload.config_id !== this.configId) return;
                
                this.isRunning = Boolean(payload.is_running);
                this.applyStatus(payload.status || {});
            });
        },
        
        // ...
    };
};
```

### 3.3 Alpine.js 컴포넌트: `statusBadge`
시스템 전반의 상태(헤더 우측 배지)를 표시합니다. 이 컴포넌트는 WebSocket 대신 **주기적 폴링(Polling)** 방식을 사용합니다.

- **구현 이유**: 단순 서버 생존 여부(Alive/Idle) 확인에는 WebSocket 연결 유지보다 단순 HTTP 요청이 가볍고 적합할 수 있음.
- **동작**: `setInterval`을 사용하여 5초마다 `/server/status.json` 엔드포인트를 호출.

---

## 4. 데이터 흐름 요약

1.  **사용자 동작**: "동기화 시작" 버튼 클릭 → `fetch` API로 POST 요청 전송 (Client → Server).
2.  **작업 시작**: 서버가 백그라운드 스레드에서 파일 동기화 작업 시작.
3.  **진행 상황**: 파일 하나가 복사될 때마다 `_emit_status_event()` 호출.
4.  **실시간 전송**: Flask-SocketIO가 연결된 모든 웹 클라이언트에 JSON 패킷 전송 (Server → Client).
5.  **UI 업데이트**: `syncStatusPanel`이 이벤트를 감지하고 Alpine.js의 Reactivity 시스템에 의해 프로그레스 바와 텍스트가 즉시 변경됨.

