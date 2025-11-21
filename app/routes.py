"""
Flask 라우트 정의 모듈

이 모듈은 애플리케이션의 모든 HTTP 라우트를 정의합니다.
HTMX를 사용한 부분 렌더링과 서버 사이드 렌더링을 결합한 하이브리드 방식으로 구현되어 있습니다.
"""
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, render_template, request, current_app, jsonify

from app import socketio
from app.db import get_db
from app.filesync import FileSyncManager, SyncConfig, validate_paths

# 전역 동기화 관리자 상태 (config_id -> {manager, thread})
sync_managers = {}

DEFAULT_SOURCE_PATH = ''
DEFAULT_REPLICA_PATH = ''
logger = logging.getLogger(__name__)


def _default_status(details="Sync stopped"):
    return {
        'state': 'STOPPED',
        'current_file': '',
        'progress_percent': 0,
        'details': details,
        'last_sync_time': '',
        'updated_at': datetime.utcnow().isoformat()
    }


def _get_status_context(config_id, details=None):
    """특정 설정 ID에 대한 상태를 반환합니다."""
    if config_id in sync_managers:
        manager = sync_managers[config_id]['manager']
        return manager.running, manager.get_status()
    
    message = details if details else "Sync stopped"
    return False, _default_status(message)


def _status_payload(config_id, is_running, status):
    return {
        "config_id": config_id,
        "is_running": is_running,
        "status": status,
    }


def _status_response(config_id, is_running, status):
    wants_json = request.accept_mimetypes["application/json"] >= request.accept_mimetypes["text/html"]
    if wants_json:
        return jsonify(_status_payload(config_id, is_running, status))
    return render_template("partials/sync_status.html", is_running=is_running, status=status, config_id=config_id)


def _build_system_status():
    """헤더에 노출할 전체 시스템 상태 정보를 계산합니다."""
    active_count = sum(
        1 for entry in sync_managers.values() if entry['manager'].running
    )
    total_configs = len(sync_managers)

    if active_count > 0:
        state = "ONLINE"
        tone = "online"
        detail = f"{active_count}개 작업 실행 중"
    elif total_configs > 0:
        state = "IDLE"
        tone = "idle"
        detail = "모든 작업 대기 중"
    else:
        state = "READY"
        tone = "ready"
        detail = "등록된 작업 없음"

    return {
        'state': state,
        'tone': tone,
        'detail': detail,
        'active_count': active_count,
        'total_configs': total_configs,
        'checked_at': datetime.utcnow().strftime("%H:%M:%S"),
    }


def _emit_status_event(config_id, is_running, status):
    try:
        socketio.emit("sync_update", _status_payload(config_id, is_running, status))
    except Exception:
        logger.exception("Failed to emit sync_update for config %s", config_id)
def _start_sync_manager(config_row, resume=False):
    """
    config_row 정보를 기반으로 FileSyncManager를 기동합니다.
    resume=True일 경우 서버 재기동 후 자동 재시작 상황을 의미합니다.
    """
    config_id = config_row['id']
    
    # 이미 실행 중인지 확인
    if config_id in sync_managers:
        manager = sync_managers[config_id]['manager']
        if manager.running:
            return True, None

    db = get_db()
    source_path = config_row['source_path'] or DEFAULT_SOURCE_PATH
    replica_path = config_row['replica_path'] or DEFAULT_REPLICA_PATH

    try:
        # 경로 사전 검증: 존재하지 않으면 즉시 실패 반환
        try:
            validate_paths(Path(source_path), Path(replica_path))
        except ValueError as exc:
            return False, str(exc)

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

        manager_holder = {}

        def status_callback(status):
            manager_instance = manager_holder.get('manager')
            is_running = bool(manager_instance and manager_instance.running)
            _emit_status_event(config_id, is_running, status or {})

        manager = FileSyncManager(sync_config, status_callback=status_callback)
        manager_holder['manager'] = manager
        thread = threading.Thread(target=manager.run, daemon=True)
        thread.start()

        sync_managers[config_id] = {
            'manager': manager,
            'thread': thread
        }

        db.execute('UPDATE sync_configs SET is_active = 1 WHERE id = ?', (config_id,))
        db.commit()

        if resume:
            current_app.logger.info(f"Resumed file sync automatically for config {config_id} after restart.")
        return True, None
    except Exception as exc:
        current_app.logger.error(f"Failed to start sync for config {config_id}: {exc}")
        db.execute('UPDATE sync_configs SET is_active = 0 WHERE id = ?', (config_id,))
        db.commit()
        return False, str(exc)


def _stop_sync_manager(config_id):
    """특정 설정 ID의 동기화 작업을 중지합니다."""
    if config_id in sync_managers:
        entry = sync_managers[config_id]
        manager = entry['manager']
        thread = entry['thread']
        
        manager.stop()
        _emit_status_event(config_id, False, manager.get_status())
        if thread.is_alive():
            thread.join(timeout=2.0)
            
        del sync_managers[config_id]
        
        # DB 상태 업데이트
        db = get_db()
        db.execute('UPDATE sync_configs SET is_active = 0 WHERE id = ?', (config_id,))
        db.commit()




# 메인 블루프린트 정의
# Blueprint를 사용하여 라우트를 모듈화하고 관리합니다
main = Blueprint('main', __name__)


@main.route('/')
def index():
    """
    메인 페이지 - 파일 동기화 설정 및 상태 페이지
    """
    db = get_db()
    # 모든 설정을 가져옴
    config_rows = db.execute('SELECT * FROM sync_configs ORDER BY id').fetchall()
    
    configs = []
    for row in config_rows:
        config = dict(row)
        config['source_path'] = config.get('source_path') or DEFAULT_SOURCE_PATH
        config['replica_path'] = config.get('replica_path') or DEFAULT_REPLICA_PATH
        
        # 각 설정에 대한 현재 상태 주입
        is_running, status = _get_status_context(config['id'])
        config['is_running'] = is_running
        config['status'] = status
        
        configs.append(config)

    # 설정이 하나도 없으면 기본 빈 설정 하나 추가 (UI에서 보여주기 위함)
    if not configs:
        configs = []

    return render_template(
        'index.html',
        configs=configs
    )


# --- FileSync 관련 라우트 ---


@main.route('/filesync/config', methods=['POST'])
def update_sync_config():
    """
    [HTMX] 설정 저장 (생성 또는 수정)
    """
    db = get_db()
    
    # 폼 데이터 추출
    name = request.form.get('name', 'Default Config').strip()
    if not name:
        name = 'Default Config'
    source_path = (request.form.get('source_path') or DEFAULT_SOURCE_PATH).strip()
    replica_path = (request.form.get('replica_path') or DEFAULT_REPLICA_PATH).strip()
    pattern = request.form.get('pattern', '*').strip() or '*'
    interval = int(request.form.get('interval', 10))
    retention_days = int(request.form.get('retention_days', 60))
    config_id = request.form.get('id')
    
    if not source_path or not replica_path:
        # 유효성 검사 실패 시 폼만 다시 렌더링 (에러 메시지 포함)
        # config_id가 있으면 기존 값, 없으면 입력값 유지
        config = {
            'id': config_id or '',
            'name': name,
            'source_path': source_path,
            'replica_path': replica_path,
            'pattern': pattern,
            'interval': interval,
            'retention_days': retention_days
        }
        return render_template(
            'partials/sync_config_form.html',
            config=config,
            message="경로를 모두 입력해주세요."
        )

    was_running = False
    if config_id:
        config_id = int(config_id)
        if config_id in sync_managers:
            manager_entry = sync_managers[config_id]
            manager = manager_entry['manager']
            was_running = manager.running
        db.execute("""
            UPDATE sync_configs 
            SET name=?, source_path=?, replica_path=?, pattern=?, interval=?, retention_days=?
            WHERE id=?
        """, (name, source_path, replica_path, pattern, interval, retention_days, config_id))
        new_id = config_id
    else:
        cursor = db.execute("""
            INSERT INTO sync_configs (name, source_path, replica_path, pattern, interval, retention_days)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, source_path, replica_path, pattern, interval, retention_days))
        new_id = cursor.lastrowid
        
    db.commit()
    
    # 업데이트된 설정 다시 조회
    config_row = db.execute('SELECT * FROM sync_configs WHERE id = ?', (new_id,)).fetchone()
    config = dict(config_row)

    restart_error = None
    if was_running:
        _stop_sync_manager(new_id)
        restarted, error_message = _start_sync_manager(config_row)
        if not restarted:
            restart_error = error_message or "재시작 실패"
            current_app.logger.error(f"Config {new_id} 재시작 실패: {restart_error}")
    
    # 상태 정보 주입
    is_running, status = _get_status_context(config['id'])
    if restart_error:
        status['details'] = f"설정 저장 후 재시작 실패: {restart_error}"
    config['is_running'] = is_running
    config['status'] = status
    
    # 저장 후에는 카드 전체를 다시 렌더링하여 상태창과 폼을 모두 갱신
    # (새로 생성된 경우 ID가 부여되어야 하므로)
    return render_template('partials/sync_card.html', config=config)


@main.route('/filesync/add', methods=['GET'])
def add_sync_config():
    """
    [HTMX] 새로운 설정 카드 추가
    """
    # 빈 설정 객체 생성
    new_config = {
        'id': '', # ID가 없으면 신규 생성 모드
        'name': 'New Config',
        'source_path': DEFAULT_SOURCE_PATH,
        'replica_path': DEFAULT_REPLICA_PATH,
        'pattern': '*',
        'interval': 10,
        'retention_days': 60
    }
    return render_template('partials/sync_card.html', config=new_config)


@main.route('/filesync/delete/<int:config_id>', methods=['DELETE'])
def delete_sync_config(config_id):
    """
    [HTMX] 설정 삭제
    """
    # 실행 중이면 중지
    _stop_sync_manager(config_id)
    
    db = get_db()
    db.execute('DELETE FROM sync_configs WHERE id = ?', (config_id,))
    db.commit()
    
    return ""  # 빈 응답을 보내면 HTMX가 요소를 DOM에서 제거함


@main.route('/filesync/status/<int:config_id>')
def get_sync_status(config_id):
    """
    [HTMX] 동기화 상태 폴링
    """
    is_running, status = _get_status_context(config_id)
    return _status_response(config_id, is_running, status)


@main.route('/filesync/status/<int:config_id>.json')
def get_sync_status_json(config_id):
    """
    JSON 형식의 동기화 상태 반환 (Alpine 폴링용)
    """
    is_running, status = _get_status_context(config_id)
    return jsonify(_status_payload(config_id, is_running, status))


@main.route('/filesync/start/<int:config_id>', methods=['POST'])
def start_sync(config_id):
    """
    [HTMX] 동기화 시작
    """
    db = get_db()
    config_row = db.execute('SELECT * FROM sync_configs WHERE id = ?', (config_id,)).fetchone()
    
    if not config_row:
        is_running, status = _get_status_context(config_id, details="설정을 찾을 수 없습니다.")
        return _status_response(config_id, is_running, status)

    success, error_message = _start_sync_manager(config_row)
    if not success:
        details = "동기화 시작 중 오류가 발생했습니다."
        if error_message:
            details = error_message
        is_running, status = _get_status_context(config_id, details=details)
        return _status_response(config_id, is_running, status)

    is_running, status = _get_status_context(config_id)
    return _status_response(config_id, is_running, status)


@main.route('/filesync/stop/<int:config_id>', methods=['POST'])
def stop_sync(config_id):
    """
    [HTMX] 동기화 중지
    """
    _stop_sync_manager(config_id)
    
    is_running, status = _get_status_context(config_id, details="Sync stopped")
    return _status_response(config_id, is_running, status)


@main.route('/server/shutdown', methods=['POST'])
def shutdown_server():
    """
    [HTMX] 서버 종료
    """
    # 모든 동기화 작업 중지
    for config_id in list(sync_managers.keys()):
        _stop_sync_manager(config_id)

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


@main.route('/server/restart', methods=['POST'])
def restart_server():
    """
    [HTMX] 서버 재시작
    """
    # 모든 동기화 작업 중지
    for config_id in list(sync_managers.keys()):
        _stop_sync_manager(config_id)

    # PID 파일 정리 (선택적)
    pid_target = os.environ.get('FILESYNC_PID_FILE')
    if pid_target and os.path.exists(pid_target):
        try:
            os.unlink(pid_target)
            current_app.logger.info("PID file removed: %s", pid_target)
        except OSError:
            pass

    # 서버 재시작: 동일한 파이썬 인터프리터로 현재 프로세스를 새로 띄우고 종료
    def delayed_restart():
        time.sleep(0.5)
        try:
            python = sys.executable
            args = [python] + sys.argv
            subprocess.Popen(args, close_fds=True)
        except Exception:
            current_app.logger.exception("Failed to spawn process for restart.")
        finally:
            os._exit(0)

    threading.Thread(target=delayed_restart, daemon=True).start()

    return "Server restarting..."


@main.route('/server/status')
def server_status():
    """
    [HTMX] 헤더 상태 뱃지를 위한 시스템 상태 엔드포인트
    """
    status = _build_system_status()
    return render_template('partials/server_status_badge.html', status=status)


@main.route('/server/status.json')
def server_status_json():
    """
    JSON 형식의 시스템 상태 엔드포인트 (Alpine.js 폴링용)
    """
    status = _build_system_status()
    return jsonify(status)


@main.before_app_request
def resume_sync_if_needed():
    """
    앱 재기동 후 이전에 실행 중이던 동기화를 자동 재개합니다.
    """
    db = get_db()
    # 활성화된 모든 설정 조회
    config_rows = db.execute('SELECT * FROM sync_configs WHERE is_active = 1').fetchall()
    
    for row in config_rows:
        _start_sync_manager(row, resume=True)
