import sqlite3
import os
from datetime import datetime
from config import DB_PATH


# FIXED: WAL Mode & 20s Timeout added to prevent SQLite locks and duplicate Telegram retries ✅
def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20) # 20s Timeout Added
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL") # WAL mode enabled for concurrent reading/writing
    return c


def init_db():
    db = _conn()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT    DEFAULT '',
            full_name     TEXT    DEFAULT '',
            registered_at TEXT,
            is_active     INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sub_id       TEXT UNIQUE,
            user_id      INTEGER,
            file_id      TEXT,
            file_name    TEXT,
            caption      TEXT    DEFAULT '',
            submitted_at TEXT,
            status       TEXT    DEFAULT 'pending',
            admin_note   TEXT    DEFAULT '',
            reviewed_at  TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            pay_id   TEXT UNIQUE,
            user_id  INTEGER,
            amount   REAL,
            note     TEXT    DEFAULT '',
            file_id  TEXT,
            sent_at  TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name   TEXT UNIQUE,
            start_time  TEXT    DEFAULT '00:00',
            end_time    TEXT    DEFAULT '23:59',
            created_at  TEXT
        );
    """)

    # Safe database migrations
    try:
        db.execute("ALTER TABLE submissions ADD COLUMN task_name TEXT DEFAULT 'General'")
    except sqlite3.OperationalError:
        pass

    try:
        db.execute("ALTER TABLE tasks ADD COLUMN start_time TEXT DEFAULT '00:00'")
        db.execute("ALTER TABLE tasks ADD COLUMN end_time TEXT DEFAULT '23:59'")
    except sqlite3.OperationalError:
        pass

    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('submissions_open', '1')")
    db.commit()
    db.close()


# ── Submissions Toggle Helpers ────────────────────────────────────────────────

def is_submissions_open():
    db = _conn()
    row = db.execute("SELECT value FROM settings WHERE key='submissions_open'").fetchone()
    db.close()
    if row:
        return row["value"] == "1"
    return True


def set_submissions_open(status: bool):
    db = _conn()
    val = "1" if status else "0"
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('submissions_open', ?)", (val,))
    db.commit()
    db.close()


# ── Tasks Management Helpers ──────────────────────────────────────────────────

def add_task(task_name, start_time="00:00", end_time="23:59"):
    db = _conn()
    try:
        db.execute(
            "INSERT INTO tasks (task_name, start_time, end_time, created_at) VALUES (?, ?, ?, ?)", 
            (task_name, start_time, end_time, datetime.now().isoformat())
        )
        db.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    db.close()
    return success


def update_task_schedule(task_id, start_time, end_time):
    db = _conn()
    db.execute("UPDATE tasks SET start_time=?, end_time=? WHERE id=?", (start_time, end_time, task_id))
    db.commit()
    db.close()


def delete_task(task_id):
    db = _conn()
    db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    db.commit()
    db.close()


def get_all_tasks():
    db = _conn()
    rows = db.execute("SELECT * FROM tasks ORDER BY id ASC").fetchall()
    db.close()
    return rows


def get_task_by_id(task_id):
    db = _conn()
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    db.close()
    return row


# ── Users ─────────────────────────────────────────────────────────────────────

def register_user(user_id, username, full_name):
    db = _conn()
    db.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name, registered_at) VALUES (?,?,?,?)",
        (user_id, username or "", full_name or "", datetime.now().isoformat())
    )
    db.execute(
        "UPDATE users SET username=?, full_name=? WHERE user_id=?",
        (username or "", full_name or "", user_id)
    )
    db.commit()
    db.close()


def get_user(user_id):
    db = _conn()
    row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    db.close()
    return row


def get_all_users():
    db = _conn()
    rows = db.execute(
        "SELECT * FROM users WHERE is_active=1 ORDER BY registered_at DESC"
    ).fetchall()
    db.close()
    return rows


# ── Submissions ───────────────────────────────────────────────────────────────

def add_submission(user_id, file_id, file_name, caption="", task_name="General"):
    db = _conn()
    n = db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    sid = f"SUB-{n+1:04d}"
    db.execute(
        "INSERT INTO submissions (sub_id,user_id,file_id,file_name,caption,task_name,submitted_at) VALUES(?,?,?,?,?,?,?)",
        (sid, user_id, file_id, file_name, caption, task_name, datetime.now().isoformat())
    )
    db.commit()
    db.close()
    return sid


def get_submission(sub_id):
    db = _conn()
    row = db.execute("SELECT * FROM submissions WHERE sub_id=?", (sub_id,)).fetchone()
    db.close()
    return row


def update_submission_status(sub_id, status, admin_note=""):
    db = _conn()
    db.execute(
        "UPDATE submissions SET status=?, admin_note=?, reviewed_at=? WHERE sub_id=?",
        (status, admin_note, datetime.now().isoformat(), sub_id)
    )
    db.commit()
    db.close()


def get_user_submissions(user_id, limit=50):
    db = _conn()
    rows = db.execute(
        "SELECT * FROM submissions WHERE user_id=? ORDER BY submitted_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    db.close()
    return rows


def get_pending_submissions():
    db = _conn()
    rows = db.execute("""
        SELECT s.*, u.username, u.full_name
        FROM submissions s JOIN users u ON s.user_id=u.user_id
        WHERE s.status='pending' ORDER BY s.submitted_at ASC
    """).fetchall()
    db.close()
    return rows


def get_all_submissions(limit=25):
    db = _conn()
    rows = db.execute("""
        SELECT s.*, u.username, u.full_name
        FROM submissions s JOIN users u ON s.user_id=u.user_id
        ORDER BY s.submitted_at DESC LIMIT ?
    """, (limit,)).fetchall()
    db.close()
    return rows


# ── Payments ──────────────────────────────────────────────────────────────────

def add_payment(user_id, amount, note="", file_id=None):
    db = _conn()
    n = db.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    pid = f"PAY-{n+1:04d}"
    db.execute(
        "INSERT INTO payments (pay_id,user_id,amount,note,file_id,sent_at) VALUES(?,?,?,?,?,?)",
        (pid, user_id, amount, note, file_id, datetime.now().isoformat())
    )
    db.commit()
    db.close()
    return pid


def get_user_payments(user_id):
    db = _conn()
    rows = db.execute(
        "SELECT * FROM payments WHERE user_id=? ORDER BY sent_at DESC",
        (user_id,)
    ).fetchall()
    db.close()
    return rows


def get_all_payments(limit=25):
    db = _conn()
    rows = db.execute("""
        SELECT p.*, u.username, u.full_name
        FROM payments p JOIN users u ON p.user_id=u.user_id
        ORDER BY p.sent_at DESC LIMIT ?
    """, (limit,)).fetchall()
    db.close()
    return rows


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats():
    db = _conn()
    c = db.cursor()
    total_users    = c.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
    total_subs     = c.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    pending        = c.execute("SELECT COUNT(*) FROM submissions WHERE status='pending'").fetchone()[0]
    approved       = c.execute("SELECT COUNT(*) FROM submissions WHERE status='approved'").fetchone()[0]
    declined       = c.execute("SELECT COUNT(*) FROM submissions WHERE status='declined'").fetchone()[0]
    total_payments = c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    total_paid     = c.execute("SELECT SUM(amount) FROM payments").fetchone()[0] or 0.0
    db.close()
    return dict(
        total_users=total_users, total_subs=total_subs,
        pending=pending, approved=approved, declined=declined,
        total_payments=total_payments, total_paid=total_paid
    )


def get_member_stats(user_id):
    """Full stats for a single member."""
    subs  = get_user_submissions(user_id)
    pays  = get_user_payments(user_id)
    total_paid = sum(p["amount"] for p in pays)
    approved   = sum(1 for s in subs if s["status"] == "approved")
    pending    = sum(1 for s in subs if s["status"] == "pending")
    declined   = sum(1 for s in subs if s["status"] == "declined")
    return dict(
        subs=subs, pays=pays, total_paid=total_paid,
        approved=approved, pending=pending, declined=declined
    )
