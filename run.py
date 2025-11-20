import signal
import sys
import os
import logging
from pathlib import Path
from app import create_app, socketio

LOG_FILE_ENV = 'FILESYNC_LOG_FILE'
PID_FILE_ENV = 'FILESYNC_PID_FILE'
_pid_file_path = None


def _configure_logging():
    log_file = os.environ.get(LOG_FILE_ENV)
    # If no external FILESYNC_LOG_FILE provided, create a timestamped log file under ./logs
    if not log_file:
        try:
            # run.py가 있는 위치(프로젝트 루트)의 logs 폴더 사용
            default_dir = Path(__file__).resolve().parent / 'logs'
            default_dir.mkdir(parents=True, exist_ok=True)
            ts = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = str(default_dir / f'filesync_{ts}.log')
        except Exception:
            log_file = None
    handlers = []
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_path, encoding='utf-8'))
        except OSError:
            pass

    if sys.stdout and hasattr(sys.stdout, 'write'):
        handlers.append(logging.StreamHandler(sys.stdout))

    if handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=handlers,
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )


_configure_logging()
app = create_app()


def _write_pid_file():
    global _pid_file_path
    pid_target = os.environ.get(PID_FILE_ENV)
    if not pid_target:
        return
    pid_path = Path(pid_target)
    try:
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()), encoding='utf-8')
        _pid_file_path = pid_path
        logging.info("PID file created at %s", pid_path)
    except OSError as exc:
        logging.error("Failed to write PID file: %s", exc)


def _cleanup_pid_file():
    global _pid_file_path
    if _pid_file_path and _pid_file_path.exists():
        try:
            _pid_file_path.unlink()
            logging.info("PID file removed: %s", _pid_file_path)
        except OSError as exc:
            logging.warning("Could not remove PID file %s: %s", _pid_file_path, exc)
    _pid_file_path = None


def signal_handler(signum, frame):
    """Signal handler for graceful shutdown"""
    logging.info("Received signal %s. Shutting down...", signum)
    _cleanup_pid_file()
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    _write_pid_file()
    try:
        logging.info("Filesync Web UI starting on port 5120")
        socketio.run(app, debug=True, use_reloader=False, port=5120)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received. Stopping server.")
    finally:
        _cleanup_pid_file()

