import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

DB_PATH = os.path.join(os.path.dirname(__file__), 'study_buddy.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Courses table
    c.execute('''CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT NOT NULL,
        course_name TEXT NOT NULL,
        department TEXT NOT NULL
    )''')

    # User courses (enrollment)
    c.execute('''CREATE TABLE IF NOT EXISTS user_courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        course_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (course_id) REFERENCES courses (id),
        UNIQUE(user_id, course_id)
    )''')

    # Study sessions
    c.execute('''CREATE TABLE IF NOT EXISTS study_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id INTEGER,
        course_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        session_date DATE,
        session_time TIME,
        duration INTEGER DEFAULT 60,
        location TEXT,
        max_participants INTEGER DEFAULT 4,
        status TEXT DEFAULT 'open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (creator_id) REFERENCES users (id),
        FOREIGN KEY (course_id) REFERENCES courses (id)
    )''')

    # Session participants
    c.execute('''CREATE TABLE IF NOT EXISTS session_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        user_id INTEGER,
        status TEXT DEFAULT 'confirmed',
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES study_sessions (id),
        FOREIGN KEY (user_id) REFERENCES users (id),
        UNIQUE(session_id, user_id)
    )''')

    # Insert sample courses
    sample_courses = [
        ('CS1010', 'Introduction to Computer Science', 'Computer Science'),
        ('MATH1060', 'Calculus I', 'Mathematics'),
        ('PHYS2070', 'University Physics I', 'Physics'),
        ('CHEM1050', 'General Chemistry', 'Chemistry'),
        ('CS2030', 'Computer Science II', 'Computer Science'),
        ('CS3240', 'Database Systems', 'Computer Science'),
        ('ENGL1010', 'English Composition I', 'English'),
        ('HIST1010', 'World History', 'History')
    ]

    c.executemany('INSERT OR IGNORE INTO courses (course_code, course_name, department) VALUES (?, ?, ?)',
                  sample_courses)

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if not username or not email or not password:
            flash('All fields are required!')
            return render_template('register.html')

        conn = get_db_connection()
        existing_user = conn.execute('SELECT id FROM users WHERE username = ? OR email = ?',
                                   (username, email)).fetchone()

        if existing_user:
            flash('Username or email already exists!')
            conn.close()
            return render_template('register.html')

        password_hash = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                    (username, email, password_hash))
        conn.commit()
        conn.close()

        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    user_courses = conn.execute('''
        SELECT c.id, c.course_code, c.course_name, c.department
        FROM courses c
        JOIN user_courses uc ON c.id = uc.course_id
        WHERE uc.user_id = ?
    ''', (session['user_id'],)).fetchall()

    upcoming_sessions = conn.execute('''
        SELECT s.*, c.course_code, c.course_name, u.username as creator_name,
               COUNT(sp.id) as participant_count
        FROM study_sessions s
        JOIN courses c ON s.course_id = c.id
        JOIN users u ON s.creator_id = u.id
        LEFT JOIN session_participants sp ON s.id = sp.session_id AND sp.status = 'confirmed'
        WHERE s.course_id IN (
            SELECT course_id FROM user_courses WHERE user_id = ?
        ) AND s.session_date >= date('now')
        GROUP BY s.id
        ORDER BY s.session_date, s.session_time
        LIMIT 5
    ''', (session['user_id'],)).fetchall()

    conn.close()

    return render_template('dashboard.html',
                         user_courses=user_courses,
                         upcoming_sessions=upcoming_sessions)

@app.route('/courses')
def courses():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    all_courses = conn.execute('SELECT * FROM courses ORDER BY department, course_code').fetchall()
    enrolled_course_ids = [row[0] for row in conn.execute(
        'SELECT course_id FROM user_courses WHERE user_id = ?',
        (session['user_id'],)
    ).fetchall()]
    conn.close()

    return render_template('courses.html',
                         all_courses=all_courses,
                         enrolled_course_ids=enrolled_course_ids)

@app.route('/enroll_course/<int:course_id>')
def enroll_course(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO user_courses (user_id, course_id) VALUES (?, ?)',
                    (session['user_id'], course_id))
        conn.commit()
        flash('Successfully enrolled in course!')
    except sqlite3.IntegrityError:
        flash('You are already enrolled in this course!')
    conn.close()
    return redirect(url_for('courses'))

@app.route('/drop_course/<int:course_id>')
def drop_course(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM user_courses WHERE user_id = ? AND course_id = ?',
                (session['user_id'], course_id))
    conn.commit()
    conn.close()

    flash('Successfully dropped course!')
    return redirect(url_for('courses'))

@app.route('/sessions')
def sessions():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    sessions = conn.execute('''
        SELECT s.*, c.course_code, c.course_name, u.username as creator_name,
               COUNT(sp.id) as participant_count,
               CASE WHEN s.creator_id = ? THEN 1 ELSE 0 END as is_creator,
               CASE WHEN sp_user.user_id IS NOT NULL THEN sp_user.status ELSE 'not_joined' END as user_status
        FROM study_sessions s
        JOIN courses c ON s.course_id = c.id
        JOIN users u ON s.creator_id = u.id
        LEFT JOIN session_participants sp ON s.id = sp.session_id AND sp.status = 'confirmed'
        LEFT JOIN session_participants sp_user ON s.id = sp_user.session_id AND sp_user.user_id = ?
        WHERE s.course_id IN (
            SELECT course_id FROM user_courses WHERE user_id = ?
        ) AND s.session_date >= date('now')
        GROUP BY s.id
        ORDER BY s.session_date, s.session_time
    ''', (session['user_id'], session['user_id'], session['user_id'])).fetchall()

    conn.close()
    return render_template('sessions.html', sessions=sessions)

@app.route('/create_session', methods=['GET', 'POST'])
def create_session():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        course_id = request.form['course_id']
        title = request.form['title']
        description = request.form['description']
        session_date = request.form['session_date']
        session_time = request.form['session_time']
        duration = request.form['duration']
        location = request.form['location']
        max_participants = request.form['max_participants']

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO study_sessions
            (creator_id, course_id, title, description, session_date, session_time,
             duration, location, max_participants)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], course_id, title, description, session_date,
              session_time, duration, location, max_participants))
        conn.commit()
        conn.close()

        flash('Study session created successfully!')
        return redirect(url_for('sessions'))

    conn = get_db_connection()
    user_courses = conn.execute('''
        SELECT c.id, c.course_code, c.course_name
        FROM courses c
        JOIN user_courses uc ON c.id = uc.course_id
        WHERE uc.user_id = ?
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return render_template('create_session.html', user_courses=user_courses)

@app.route('/join_session/<int:session_id>')
def join_session(session_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO session_participants (session_id, user_id) VALUES (?, ?)',
                    (session_id, session['user_id']))
        conn.commit()
        flash('Successfully joined study session!')
    except sqlite3.IntegrityError:
        flash('You have already joined this session!')
    conn.close()
    return redirect(url_for('sessions'))

@app.route('/leave_session/<int:session_id>')
def leave_session(session_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM session_participants WHERE session_id = ? AND user_id = ?',
                (session_id, session['user_id']))
    conn.commit()
    conn.close()

    flash('You have left the study session.')
    return redirect(url_for('sessions'))

