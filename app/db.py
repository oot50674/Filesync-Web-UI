import sqlite3
import click
from flask import current_app, g

def get_db():
    """
    애플리케이션 컨텍스트 동안 데이터베이스 연결을 유지하고 반환합니다.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        # Row 객체를 사용하여 컬럼 이름으로 접근 가능하게 설정
        g.db.row_factory = sqlite3.Row

    return g.db

def close_db(e=None):
    """
    애플리케이션 컨텍스트가 종료될 때 데이터베이스 연결을 닫습니다.
    """
    db = g.pop('db', None)

    if db is not None:
        db.close()

def init_db():
    """
    schema.sql 파일을 읽어 데이터베이스를 초기화합니다.
    """
    db = get_db()

    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))

@click.command('init-db')
def init_db_command():
    """기존 데이터를 삭제하고 새 테이블을 생성합니다."""
    init_db()
    click.echo('Initialized the database.')

def init_app(app):
    """
    Flask 앱에 DB 관련 정리 함수와 명령어를 등록합니다.
    """
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def ensure_schema_upgrades():
    """
    기존 DB에 누락된 컬럼이 있으면 자동으로 추가합니다.
    """
    db = get_db()
    table_info = db.execute("PRAGMA table_info(sync_configs)").fetchall()
    if not table_info:
        return

    columns = {row["name"] for row in table_info}
    altered = False

    if "retention_mode" not in columns:
        db.execute(
            "ALTER TABLE sync_configs ADD COLUMN retention_mode TEXT DEFAULT 'days'"
        )
        altered = True

    if "retention_files" not in columns:
        db.execute(
            "ALTER TABLE sync_configs ADD COLUMN retention_files INTEGER DEFAULT 0"
        )
        altered = True

    if altered:
        db.commit()

