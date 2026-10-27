import json
import os
import re
import sqlite3
from urllib.parse import urlparse
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('DATABASE_PATH', BASE_DIR / 'instance' / 'sikpumta.sqlite3'))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-only-change-this-secret-before-deploying'),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '0') == '1',
    PERMANENT_SESSION_LIFETIME=timedelta(days=14),
    MAX_CONTENT_LENGTH=1_000_000,
)


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    with connect_db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS user_state (
            user_id INTEGER PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')


init_db()


def current_user_id():
    value = session.get('user_id')
    return int(value) if value is not None else None


def json_error(message, status):
    return jsonify({'error': message}), status


def same_origin_write_required():
    # Modern browsers send Origin on fetch POST/PUT. If present, reject cross-site writes.
    origin = request.headers.get('Origin')
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
        return parsed.netloc.lower() == request.host.lower() and parsed.scheme in ('http', 'https')
    except ValueError:
        return False


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/healthz')
def healthz():
    return jsonify({'ok': True})


@app.get('/api/me')
def me():
    uid = current_user_id()
    if uid is None:
        return jsonify({'authenticated': False})
    with connect_db() as db:
        user = db.execute('SELECT id, email FROM users WHERE id = ?', (uid,)).fetchone()
    if not user:
        session.clear()
        return jsonify({'authenticated': False})
    return jsonify({'authenticated': True, 'email': user['email']})


@app.post('/api/register')
def register():
    if not same_origin_write_required():
        return json_error('허용되지 않은 요청입니다.', 403)
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return json_error('올바른 이메일 주소를 입력해 주세요.', 400)
    if len(password) < 8 or len(password) > 128:
        return json_error('비밀번호는 8자 이상 128자 이하로 입력해 주세요.', 400)
    try:
        with connect_db() as db:
            cur = db.execute('INSERT INTO users(email, password_hash) VALUES (?, ?)',
                             (email, generate_password_hash(password, method='pbkdf2:sha256')))
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        return json_error('이미 가입된 이메일이에요. 로그인해 주세요.', 409)
    session.clear()
    session['user_id'] = uid
    session.permanent = True
    return jsonify({'ok': True, 'is_new': True, 'email': email}), 201


@app.post('/api/login')
def login():
    if not same_origin_write_required():
        return json_error('허용되지 않은 요청입니다.', 403)
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    with connect_db() as db:
        user = db.execute('SELECT id, email, password_hash FROM users WHERE email = ?', (email,)).fetchone()
    if not user or not check_password_hash(user['password_hash'], password):
        return json_error('이메일 또는 비밀번호가 맞지 않아요.', 401)
    session.clear()
    session['user_id'] = user['id']
    session.permanent = True
    return jsonify({'ok': True, 'is_new': False, 'email': user['email']})


@app.post('/api/logout')
def logout():
    if not same_origin_write_required():
        return json_error('허용되지 않은 요청입니다.', 403)
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/state', methods=['GET', 'PUT'])
def state():
    uid = current_user_id()
    if uid is None:
        return json_error('로그인이 필요해요.', 401)
    if request.method == 'GET':
        with connect_db() as db:
            row = db.execute('SELECT state_json, updated_at FROM user_state WHERE user_id = ?', (uid,)).fetchone()
        if not row:
            return jsonify({'state': None, 'updated_at': None})
        try:
            state_data = json.loads(row['state_json'])
        except json.JSONDecodeError:
            return json_error('저장된 데이터 형식이 올바르지 않아요.', 500)
        return jsonify({'state': state_data, 'updated_at': row['updated_at']})

    if not same_origin_write_required():
        return json_error('허용되지 않은 요청입니다.', 403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error('저장할 데이터 형식이 올바르지 않아요.', 400)
    # Avoid accidentally accepting arbitrarily large or malformed client state.
    try:
        serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    except (TypeError, ValueError):
        return json_error('데이터를 저장할 수 없는 형식이에요.', 400)
    if len(serialized.encode('utf-8')) > 900_000:
        return json_error('저장 데이터가 너무 커요.', 413)
    with connect_db() as db:
        db.execute('''INSERT INTO user_state(user_id, state_json, updated_at)
                      VALUES (?, ?, CURRENT_TIMESTAMP)
                      ON CONFLICT(user_id) DO UPDATE SET
                      state_json = excluded.state_json,
                      updated_at = CURRENT_TIMESTAMP''', (uid, serialized))
    return jsonify({'ok': True})


@app.after_request
def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)
