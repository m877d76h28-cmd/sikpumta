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

@app.get('/api/leaderboard')
def leaderboard():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    KST = ZoneInfo('Asia/Seoul')
    now = datetime.now(KST)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result = []

    with connect_db() as db:
        rows = db.execute('''
            SELECT users.id, user_state.state_json
            FROM users
            LEFT JOIN user_state ON users.id = user_state.user_id
        ''').fetchall()

        for row in rows:
            try:
                data = json.loads(row['state_json'] or '{}')
            except (json.JSONDecodeError, TypeError):
                continue

            profile = data.get('profile') or {}
            name = str(profile.get('name') or '사용자')
            logs = data.get('logs') or []
            meals = data.get('meals') or []
            focus = data.get('focus') or []
            study = data.get('study') or []

            bed = str(data.get('bed') or '23:30')
            try:
                hh, mm = map(int, bed.split(':'))
                bed_min = hh * 60 + mm
            except (ValueError, TypeError):
                bed_min = 23 * 60 + 30

            if bed_min < 720:
                bed_min += 1440

            try:
                hl = float(data.get('hl') or 5.5)
            except (ValueError, TypeError):
                hl = 5.5

            cutoff = bed_min - hl * 60 * 6 / 5.5

            try:
                age = float(profile.get('age') or 0)
                weight = float(profile.get('weight') or data.get('kg') or 60)
            except (ValueError, TypeError):
                age, weight = 0, 60

            limit = 400 if age >= 19 else min(150, round(weight * 2.5))
            if profile.get('pregnant') == 'yes':
                limit = 300

            health = 0
            minutes = 0

            for i in range(7):
                start = today - timedelta(days=i)
                end = start + timedelta(days=1)
                start_ms = start.timestamp() * 1000
                end_ms = end.timestamp() * 1000

                day_logs = [
                    x for x in logs
                    if start_ms <= (x.get('t') or 0) < end_ms
                ]
                day_meals = [
                    x for x in meals
                    if start_ms <= (x.get('t') or 0) < end_ms
                ]
                day_study = [
                    x for x in study
                    if start_ms <= (x.get('t') or 0) < end_ms
                ]
                day_focus = [
                    x for x in focus
                    if start_ms <= (x.get('t') or 0) < end_ms
                ]

                if not (day_logs or day_meals or day_study or day_focus):
                    continue

                late = any(
                    ((x.get('t') or 0) - start_ms) / 60000 > cutoff
                    for x in day_logs
                )
                caffeine = sum(
                    float(x.get('mg') or 0) for x in day_logs
                )

                health += 0 if late else 10
                health += 0 if caffeine > limit else 5
                health += 5 if day_meals else 0
                minutes += sum(
                    max(0, float(x.get('m') or 0))
                    for x in day_study
                )

            health += min(30, max(0, float(data.get('gw') or 0) * 3))
            study_score = min(120, round(minutes / 5))
            result.append({
                'name': name[:40],
                'health': round(health),
                'study': study_score,
                'score': round(health) + study_score,
                'is_me': row['id'] == session.get('user_id')
            })

    result.sort(key=lambda x: x['score'], reverse=True)
    return jsonify({'rankings': result})
@app.after_request
def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)
