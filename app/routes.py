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
    else:
        config = {
            'id': '',
            'name': 'Default Config',
            'source_path': '',
            'replica_path': '',
            'pattern': '*',
            'interval': 10,
            'retention_days': 60
        }

    is_running, status = _get_status_context()
    return render_template('index.html', config=config, is_running=is_running, status=status)




# --- FileSync 관련 라우트 ---


@main.route('/filesync/config', methods=['POST'])
def update_sync_config():
    """
    [HTMX] 설정 저장
    """
    db = get_db()
    
    # 폼 데이터 추출
    name = request.form.get('name', 'Default Config')
    source_path = request.form.get('source_path')
    replica_path = request.form.get('replica_path')
    pattern = request.form.get('pattern', '*')
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

    try:
        # Config 객체 생성
        sync_config = SyncConfig(
            source=Path(config_row['source_path']),
            destination=Path(config_row['replica_path']),
            pattern=config_row['pattern'],
            retention_days=config_row['retention_days'],
            scan_interval=config_row['interval']
        )

        # 동기화 스레드 시작 전에 로그 구성 (CLI와 동일하게 INFO 레벨 설정)
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )

        # Manager 초기화 및 스레드 시작
        manager = FileSyncManager(sync_config)
        thread = threading.Thread(target=manager.run, daemon=True)
        thread.start()

        sync_state['manager'] = manager
        sync_state['thread'] = thread

        # DB 상태 업데이트 (선택 사항)
        db.execute('UPDATE sync_configs SET is_active = 1 WHERE id = ?', (config_row['id'],))
        db.commit()

        is_running, status = _get_status_context()
        return render_template('partials/sync_status.html', is_running=is_running, status=status)
    except Exception as e:
        current_app.logger.error(f"Failed to start sync: {e}")
        is_running, status = _get_status_context(details="동기화 시작 중 오류가 발생했습니다.")
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
