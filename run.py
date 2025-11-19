import signal
import sys
from app import create_app

app = create_app()

def signal_handler(signum, frame):
    """Signal handler for graceful shutdown"""
    print("\n서버를 종료합니다...")
    sys.exit(0)

if __name__ == '__main__':
    # 터미널 종료 시그널 처리 등록
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # 백그라운드 리로더와 스레딩 비활성화
        app.run(debug=True, use_reloader=False, threaded=False, port=5120)
    except KeyboardInterrupt:
        print("\n서버를 종료합니다...")
        sys.exit(0)

