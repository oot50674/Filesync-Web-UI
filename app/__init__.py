from flask import Flask
import os

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

    # 블루프린트(라우트) 등록
    from .routes import main
    app.register_blueprint(main)

    return app
