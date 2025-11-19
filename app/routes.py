"""
Flask 라우트 정의 모듈

이 모듈은 애플리케이션의 모든 HTTP 라우트를 정의합니다.
HTMX를 사용한 부분 렌더링과 서버 사이드 렌더링을 결합한 하이브리드 방식으로 구현되어 있습니다.
"""
from flask import Blueprint, render_template, request, current_app
from datetime import datetime
import threading
import logging
from pathlib import Path
from app.db import get_db
from app.filesync import FileSyncManager, SyncConfig

# 전역 동기화 관리자 상태 (간단한 싱글톤 패턴)
sync_state = {
    'manager': None,
    'thread': None
}

DEFAULT_SOURCE_PATH = ''
DEFAULT_REPLICA_PATH = ''


def _default_status(details="Sync stopped"):
    return {
        'state': 'STOPPED',
        'current_file': '',
        'progress_percent': 0,
        'details': details,
        'last_sync_time': '',
        'updated_at': datetime.utcnow().isoformat()
    }


def _get_status_context(details=None):
    manager = sync_state['manager']
    if manager:
        return manager.running, manager.get_status()
    message = details if details else "Sync stopped"
    return False, _default_status(message)


def _start_sync_manager(config_row, resume=False):
    """
    config_row 정보를 기반으로 FileSyncManager를 기동합니다.
    resume=True일 경우 서버 재기동 후 자동 재시작 상황을 의미합니다.
    """
    if sync_state['manager'] and sync_state['manager'].running:
        return True, None

    db = get_db()
    source_path = config_row['source_path'] or DEFAULT_SOURCE_PATH
    replica_path = config_row['replica_path'] or DEFAULT_REPLICA_PATH

    try:
        sync_config = SyncConfig(
            source=Path(source_path),
            destination=Path(replica_path),
            pattern=config_row['pattern'],
            retention_days=config_row['retention_days'],
            scan_interval=config_row['interval']
        )

        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )

        manager = FileSyncManager(sync_config)
        thread = threading.Thread(target=manager.run, daemon=True)
        thread.start()

        sync_state['manager'] = manager
        sync_state['thread'] = thread

        db.execute('UPDATE sync_configs SET is_active = 1 WHERE id = ?', (config_row['id'],))
        db.commit()

        if resume:
            current_app.logger.info("Resumed file sync automatically after restart.")
        return True, None
    except Exception as exc:
        current_app.logger.error(f"Failed to start sync: {exc}")
        db.execute('UPDATE sync_configs SET is_active = 0 WHERE id = ?', (config_row['id'],))
        db.commit()
        return False, str(exc)



# 메인 블루프린트 정의
# Blueprint를 사용하여 라우트를 모듈화하고 관리합니다
main = Blueprint('main', __name__)


@main.route('/')
def index():
    """
    메인 페이지 - 파일 동기화 설정 및 상태 페이지
    """
    db = get_db()
    # 첫 번째 설정을 가져오거나 없으면 기본값 사용
    config_row = db.execute('SELECT * FROM sync_configs ORDER BY id LIMIT 1').fetchone()

    if config_row:
        config = dict(config_row)
        config['source_path'] = config.get('source_path') or DEFAULT_SOURCE_PATH
        config['replica_path'] = config.get('replica_path') or DEFAULT_REPLICA_PATH
    else:
        config = {
            'id': '',
            'name': 'Default Config',
            'source_path': DEFAULT_SOURCE_PATH,
            'replica_path': DEFAULT_REPLICA_PATH,
            'pattern': '*',
            'interval': 10,
            'retention_days': 60
        }

    is_running, status = _get_status_context()
    return render_template(
        'index.html',
        config=config,
        is_running=is_running,
        status=status
    )




# --- FileSync 관련 라우트 ---


@main.route('/filesync/config', methods=['POST'])
def update_sync_config():
    """
    [HTMX] 설정 저장
    """
    db = get_db()
    
    # 폼 데이터 추출
    name = request.form.get('name', 'Default Config').strip()
    if not name:
        name = 'Default Config'
    source_path = (request.form.get('source_path') or DEFAULT_SOURCE_PATH).strip()
    replica_path = (request.form.get('replica_path') or DEFAULT_REPLICA_PATH).strip()
    if not source_path or not replica_path:
        return render_template(
            'partials/sync_config_form.html',
            config={
                'id': config_id or '',
                'name': name,
                'source_path': source_path,
                'replica_path': replica_path,
                'pattern': pattern,
                'interval': interval,
                'retention_days': retention_days
            },
            message="경로를 모두 입력해주세요."
        )
    pattern = request.form.get('pattern', '*').strip() or '*'
    interval = int(request.form.get('interval', 10))
    retention_days = int(request.form.get('retention_days', 60))
    config_id = request.form.get('id')
    
    if config_id:
        db.execute("""
            UPDATE sync_configs 
            SET name=?, source_path=?, replica_path=?, pattern=?, interval=?, retention_days=?
            WHERE id=?
        """, (name, source_path, replica_path, pattern, interval, retention_days, config_id))
    else:
        db.execute("""
            INSERT INTO sync_configs (name, source_path, replica_path, pattern, interval, retention_days)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, source_path, replica_path, pattern, interval, retention_days))
        
    db.commit()
    
    # 업데이트된 설정 다시 조회
    config_row = db.execute('SELECT * FROM sync_configs ORDER BY id LIMIT 1').fetchone()
    config = dict(config_row)
    config['source_path'] = config.get('source_path') or DEFAULT_SOURCE_PATH
    config['replica_path'] = config.get('replica_path') or DEFAULT_REPLICA_PATH
    
    return render_template('partials/sync_config_form.html', config=config, message="설정이 저장되었습니다.")


@main.route('/filesync/status')
def get_sync_status():
    """
    [HTMX] 동기화 상태 폴링
    """
    is_running, status = _get_status_context()
    return render_template('partials/sync_status.html', is_running=is_running, status=status)


@main.route('/filesync/start', methods=['POST'])
def start_sync():
    """
    [HTMX] 동기화 시작
    """
    if sync_state['manager'] and sync_state['manager'].running:
        is_running, status = _get_status_context()
        return render_template('partials/sync_status.html', is_running=is_running, status=status)

    db = get_db()
    config_row = db.execute('SELECT * FROM sync_configs ORDER BY id LIMIT 1').fetchone()
    
    if not config_row:
        # 설정이 없으면 시작 불가
        is_running, status = _get_status_context(details="동기화 설정이 필요합니다.")
        return render_template('partials/sync_status.html', is_running=is_running, status=status)

    success, error_message = _start_sync_manager(config_row)
    if not success:
        details = "동기화 시작 중 오류가 발생했습니다."
        if error_message:
            details = f"{details} ({error_message})"
        is_running, status = _get_status_context(details=details)
        return render_template('partials/sync_status.html', is_running=is_running, status=status)

    is_running, status = _get_status_context()
    return render_template('partials/sync_status.html', is_running=is_running, status=status)


@main.route('/filesync/stop', methods=['POST'])
def stop_sync():
    """
    [HTMX] 동기화 중지
    """
    if sync_state['manager']:
        sync_state['manager'].stop()
        if sync_state['thread']:
            sync_state['thread'].join(timeout=2.0)
            
    sync_state['manager'] = None
    sync_state['thread'] = None
    
    # DB 상태 업데이트
    db = get_db()
    db.execute('UPDATE sync_configs SET is_active = 0')
    db.commit()
    
    is_running, status = _get_status_context(details="Sync stopped")
    return render_template('partials/sync_status.html', is_running=is_running, status=status)


@main.route('/server/shutdown', methods=['POST'])
def shutdown_server():
    """
    [HTMX] 서버 종료
    """
    import os
    import threading
    import time

    # 동기화 작업이 실행 중이면 먼저 중지
    if sync_state['manager'] and sync_state['manager'].running:
        sync_state['manager'].stop()
        if sync_state['thread']:
            sync_state['thread'].join(timeout=2.0)

    # PID 파일 정리
    pid_target = os.environ.get('FILESYNC_PID_FILE')
    if pid_target and os.path.exists(pid_target):
        try:
            os.unlink(pid_target)
            current_app.logger.info("PID file removed: %s", pid_target)
        except OSError:
            pass

    # 서버 종료를 별도 스레드에서 실행 (응답을 먼저 보내기 위해)
    def delayed_shutdown():
        time.sleep(0.5)  # 클라이언트 응답을 위한 약간의 지연
        os._exit(0)

    threading.Thread(target=delayed_shutdown, daemon=True).start()

    return "Server shutting down..."


@main.before_app_request
def resume_sync_if_needed():
    """
    앱 재기동 후 이전에 실행 중이던 동기화를 자동 재개합니다.
    """
    db = get_db()
    config_row = db.execute('SELECT * FROM sync_configs WHERE is_active = 1 ORDER BY id LIMIT 1').fetchone()
    if not config_row:
        return
    _start_sync_manager(config_row, resume=True)
