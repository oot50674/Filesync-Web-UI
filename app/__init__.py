from flask import Flask
import os
import logging
from flask_socketio import SocketIO

socketio = SocketIO(async_mode='threading')

def create_app():
    # Flask 앱 인스턴스 생성
    app = Flask(__name__)

    # 설정 로드
    app.config['SECRET_KEY'] = 'dev-key-please-change'
    
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
    from .routes import main
    app.register_blueprint(main)
    
    # 테스트 블루프린트 등록
    from .test import test_bp
    app.register_blueprint(test_bp)

    # SocketIO 초기화
    socketio.init_app(app, async_mode='threading')

    return app
