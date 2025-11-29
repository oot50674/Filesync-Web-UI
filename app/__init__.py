from flask import Flask
import os
import logging
import secrets
from flask_socketio import SocketIO

socketio = SocketIO(async_mode='threading')

def create_app():
    # Flask 앱 인스턴스 생성
    app = Flask(__name__)

    # 설정 로드
    # `.env` 파일에서 SECRET_KEY를 읽고, 없으면 난수로 생성해 저장합니다.
    # 프로젝트 루트(앱 폴더의 상위) 경로에 `.env` 파일을 유지합니다.
    def _ensure_secret_key():
        """ .env에 SECRET_KEY가 있으면 반환하고, 없으면 생성하여 저장한 뒤 반환합니다.

        반환값은 문자열이며, 파일에 `SECRET_KEY=<value>` 형식으로 저장됩니다.
        """
        project_root = os.path.join(app.root_path, '..')
        env_path = os.path.join(project_root, '.env')

        secret = None
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if line.startswith('SECRET_KEY='):
                            # 값은 등호 뒤 전체 (따옴표 없이 저장됨)
                            secret = line.split('=', 1)[1]
                            break
            except Exception:
                secret = None

        if not secret:
            # 안전한 난수 비밀키 생성
            secret = secrets.token_urlsafe(32)
            # .env 파일에 추가(파일이 없으면 생성)
            try:
                os.makedirs(os.path.dirname(env_path), exist_ok=True)
                # 기존 내용을 보존하고 끝에 추가
                with open(env_path, 'a', encoding='utf-8') as f:
                    f.write('\nSECRET_KEY=' + secret + '\n')
            except Exception:
                # 파일 쓰기가 실패하더라도 메모리 내에서만 사용
                pass

        return secret

    app.config['SECRET_KEY'] = _ensure_secret_key()
    
    # DB 경로 설정 (instance 폴더 안이나 프로젝트 루트에 저장)
    app.config['DATABASE'] = os.path.join(app.root_path, '..', 'database.db')

    # DB 초기화 등록
    from . import db
    db.init_app(app)

    # 서버 기동 시 DB 파일이 없으면 자동으로 스키마를 적용
    database_path = app.config['DATABASE']
    if not os.path.exists(database_path):
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        with app.app_context():
            db.init_db()

    # 누락된 컬럼 자동 보정
    with app.app_context():
        db.ensure_schema_upgrades()

    # 블루프린트(라우트) 등록
    from . import routes
    app.register_blueprint(routes.main)
    
    # 테스트 블루프린트 등록
    from .test import test_bp
    app.register_blueprint(test_bp)

    # SocketIO 초기화
    socketio.init_app(app, async_mode='threading')

    # 서버 기동 시 활성화된 작업 자동 재개
    with app.app_context():
        routes.resume_active_syncs()

    return app
