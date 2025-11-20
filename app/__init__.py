from flask import Flask
import os
import logging


class StatusPollingFilter(logging.Filter):
    """HTMX 상태 폴링 라우트(GET /filesync/status) 로그를 숨기기 위한 필터"""

    def filter(self, record):
        message = record.getMessage()
        suppressed_paths = ("/filesync/status", "/server/status")
        return not any(path in message for path in suppressed_paths)


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

    # 블루프린트(라우트) 등록
    from .routes import main
    app.register_blueprint(main)

    # 불필요한 상태 폴링 로그(werkzeug) 필터링
    werkzeug_logger = logging.getLogger("werkzeug")
    already_registered = any(
        isinstance(f, StatusPollingFilter) for f in werkzeug_logger.filters
    )
    if not already_registered:
        werkzeug_logger.addFilter(StatusPollingFilter())

    return app
