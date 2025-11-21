from flask import Blueprint, render_template
from . import socketio
import time
from flask_socketio import emit

# 테스트용 블루프린트 생성
test_bp = Blueprint('test', __name__)

# 백그라운드 스레드 상태 관리
thread = None
server_socket_active = True  # 서버 소켓 통신 활성화 플래그

def background_time_sender():
    """1초마다 서버 시간을 모든 클라이언트에게 전송.
    server_socket_active가 False로 설정되면 루프를 빠져나와 전송을 중단합니다."""
    global server_socket_active
    while server_socket_active:
        time.sleep(1)
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        socketio.emit('server_time', {'time': timestamp})
    print('Background time sender stopped.')

@test_bp.route('/test')
def test_page():
    """테스트 페이지 렌더링"""
    return render_template('test.html')

@socketio.on('connect')
def handle_connect():
    """클라이언트 연결 시 백그라운드 태스크 시작 (없으면 생성)"""
    global thread
    if thread is None:
        # 백그라운드 스레드 시작
        thread = socketio.start_background_task(background_time_sender)
    print('Client connected')

@socketio.on('client_message')
def handle_client_message(data):
    """클라이언트로부터 텍스트 메시지를 수신하여 서버 로그에 출력"""
    message = data.get('message', '')
    print(f'[클라이언트 메시지] {message}')


@socketio.on('terminate_server_socket')
def handle_terminate_server_socket(data):
    """서버의 소켓 통신을 종료: 모든 클라이언트에 알리고 내부 전송 루프를 중지"""
    global server_socket_active
    reason = data.get('reason', 'manual')
    server_socket_active = False
    print(f'[서버 소켓] 종료 명령 수신 (reason={reason})')
    # 모든 클라이언트에게 서버 종료 이벤트 브로드캐스트
    socketio.emit('server_shutdown', {'reason': reason})

