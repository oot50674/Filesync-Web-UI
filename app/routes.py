"""
Flask 라우트 정의 모듈

이 모듈은 애플리케이션의 모든 HTTP 라우트를 정의합니다.
HTMX를 사용한 부분 렌더링과 서버 사이드 렌더링을 결합한 하이브리드 방식으로 구현되어 있습니다.
"""
from flask import Blueprint, render_template, request, current_app, jsonify
from datetime import datetime
import threading
import logging
import platform
import string
import ctypes
from pathlib import Path
from app.db import get_db
from app.filesync import FileSyncManager, SyncConfig

# 전역 동기화 관리자 상태 (간단한 싱글톤 패턴)
sync_state = {
    'manager': None,
    'thread': None
}

MAX_MOUNT_VOLUMES = 5
DEFAULT_SOURCE_PATH = '/C_Drive'
DEFAULT_REPLICA_PATH = '/app/sync_replica'
MOUNT_ROOT = '/app/mounts'


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


def _serialize_mount(row):
    return {
        'id': row['id'],
        'name': row['name'],
        'host_path': row['host_path'],
        'container_path': row['container_path'],
        'display_order': row['display_order'],
        'is_enabled': bool(row['is_enabled'])
    }


def _allocated_container_path(db):
    rows = db.execute('SELECT container_path FROM mount_volumes').fetchall()
    used = {row['container_path'] for row in rows}
    for index in range(1, MAX_MOUNT_VOLUMES + 1):
        candidate = f"{MOUNT_ROOT}/mount_{index}"
        if candidate not in used:
            return candidate
    return None


def _is_windows_platform():
    return platform.system().lower().startswith('win')


def _windows_drive_label(drive_path):
    try:
        volume_name = ctypes.create_unicode_buffer(1024)
        file_system_name = ctypes.create_unicode_buffer(1024)
        result = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive_path),
            volume_name,
            len(volume_name),
            None,
            None,
            None,
            file_system_name,
            len(file_system_name)
        )
        if result:
            return volume_name.value or drive_path
    except Exception:
        return drive_path
    return drive_path


def list_windows_drives():
    if not _is_windows_platform():
        return []
    drives = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                path = f'{letter}:/'
                drives.append({
                    'letter': letter,
                    'path': path,
                    'label': _windows_drive_label(path)
                })
            bitmask >>= 1
    except Exception:
        current_app.logger.warning('드라이브 정보를 가져오지 못했습니다.')
    return drives


def _json_error(message, status_code=400):
    response = jsonify({'error': message})
    response.status_code = status_code
    return response

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
        status=status,
        max_mounts=MAX_MOUNT_VOLUMES,
        active_page='sync',
        default_source=DEFAULT_SOURCE_PATH
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
    replica_path = DEFAULT_REPLICA_PATH
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

    try:
        source_path = config_row['source_path'] or DEFAULT_SOURCE_PATH
        replica_path = config_row['replica_path'] or DEFAULT_REPLICA_PATH
        # Config 객체 생성
        sync_config = SyncConfig(
            source=Path(source_path),
            destination=Path(replica_path),
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


# --- Mount 관리 및 드라이브 관련 API ---


@main.route('/api/mounts', methods=['GET'])
def list_mounts():
    db = get_db()
    rows = db.execute('SELECT * FROM mount_volumes ORDER BY display_order, id').fetchall()
    mounts = [_serialize_mount(row) for row in rows]
    response = {
        'mounts': mounts,
        'max_mounts': MAX_MOUNT_VOLUMES,
        'current_count': len(mounts)
    }
    return jsonify(response)


@main.route('/api/mounts', methods=['POST'])
def create_mount():
    db = get_db()
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    host_path = (payload.get('host_path') or '').strip()
    display_order = payload.get('display_order')
    is_enabled = payload.get('is_enabled', True)

    if not name or not host_path:
        return _json_error('이름과 호스트 경로는 필수입니다.')

    count_row = db.execute('SELECT COUNT(*) as total FROM mount_volumes').fetchone()
    if count_row['total'] >= MAX_MOUNT_VOLUMES:
        return _json_error('더 이상 마운트를 추가할 수 없습니다. (최대 {0}개)'.format(MAX_MOUNT_VOLUMES))

    existing = db.execute('SELECT id FROM mount_volumes WHERE host_path = ?', (host_path,)).fetchone()
    if existing:
        return _json_error('이미 등록된 호스트 경로입니다.')

    container_path = _allocated_container_path(db)
    if not container_path:
        return _json_error('사용 가능한 컨테이너 경로가 없습니다.')

    if display_order is None:
        display_order = count_row['total']
    try:
        order_value = int(display_order)
    except ValueError:
        order_value = count_row['total']

    db.execute(
        '''
        INSERT INTO mount_volumes (name, host_path, container_path, display_order, is_enabled)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (name, host_path, container_path, order_value, 1 if is_enabled else 0)
    )
    db.commit()

    row = db.execute('SELECT * FROM mount_volumes WHERE host_path = ?', (host_path,)).fetchone()
    return jsonify({'mount': _serialize_mount(row)})


@main.route('/api/mounts/<int:mount_id>', methods=['PUT'])
def update_mount(mount_id):
    db = get_db()
    payload = request.get_json(silent=True) or {}
    row = db.execute('SELECT * FROM mount_volumes WHERE id = ?', (mount_id,)).fetchone()
    if not row:
        return _json_error('대상을 찾을 수 없습니다.', 404)

    name = payload.get('name', row['name'])
    host_path = payload.get('host_path', row['host_path'])
    display_order = payload.get('display_order', row['display_order'])
    is_enabled = payload.get('is_enabled', row['is_enabled'])

    name = (name or '').strip()
    host_path = (host_path or '').strip()
    if not name or not host_path:
        return _json_error('이름과 호스트 경로는 필수입니다.')

    existing = db.execute('SELECT id FROM mount_volumes WHERE host_path = ? AND id != ?', (host_path, mount_id)).fetchone()
    if existing:
        return _json_error('이미 등록된 호스트 경로입니다.')

    try:
        order_value = int(display_order)
    except ValueError:
        order_value = row['display_order']

    db.execute(
        '''
        UPDATE mount_volumes
        SET name = ?, host_path = ?, display_order = ?, is_enabled = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''',
        (name, host_path, order_value, 1 if is_enabled else 0, mount_id)
    )
    db.commit()

    updated = db.execute('SELECT * FROM mount_volumes WHERE id = ?', (mount_id,)).fetchone()
    return jsonify({'mount': _serialize_mount(updated)})


@main.route('/api/mounts/<int:mount_id>', methods=['DELETE'])
def delete_mount(mount_id):
    db = get_db()
    row = db.execute('SELECT * FROM mount_volumes WHERE id = ?', (mount_id,)).fetchone()
    if not row:
        return _json_error('대상을 찾을 수 없습니다.', 404)

    db.execute('DELETE FROM mount_volumes WHERE id = ?', (mount_id,))
    db.commit()
    return jsonify({'deleted_id': mount_id})


@main.route('/api/drives', methods=['GET'])
def api_drives():
    drives = list_windows_drives()
    return jsonify({
        'drives': drives,
        'platform': platform.system()
    })


@main.route('/mounts')
def mounts_page():
    return render_template(
        'mounts.html',
        max_mounts=MAX_MOUNT_VOLUMES,
        active_page='mounts'
    )
