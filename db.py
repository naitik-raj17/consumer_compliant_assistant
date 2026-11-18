import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import bcrypt

import config

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'consumer' CHECK(role IN ('consumer','admin')),
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS cases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    text TEXT NOT NULL,
    value REAL NOT NULL,
    state TEXT NOT NULL,
    district TEXT,
    category TEXT,
    forum TEXT,
    opposite_party TEXT,
    draft TEXT,
    status TEXT NOT NULL DEFAULT 'submitted'
        CHECK(status IN ('submitted','under_review','drafted','resolved','rejected')),
    admin_note TEXT,
    pdf_path TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS templates(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kb_chunks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    category TEXT,
    text TEXT NOT NULL,
    embedding BLOB
);
CREATE TABLE IF NOT EXISTS notifications(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    msg TEXT NOT NULL,
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_user ON cases(user_id);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, read);
"""

_VERIFICATION = """VERIFICATION:
I, {complainant}, the Complainant above named, do hereby verify that the contents of the above paragraphs are true and correct to the best of my knowledge and belief, and that nothing material has been concealed therefrom.
Verified at {district}, {state} on {date}."""

_RELIEF = """RELIEF SOUGHT:
In view of the above, the Complainant prays that this Commission may be pleased to:
(a) {relief_main};
(b) award compensation for mental agony and harassment caused to the Complainant;
(c) award the cost of litigation;
(d) pass any other order deemed fit in the interest of justice."""

SEED_TEMPLATES = [
    ("ecommerce", """FACTS OF THE CASE:
1. The Complainant, {complainant}, is a consumer within the meaning of Section 2(7) of the Consumer Protection Act, 2019, having purchased goods/services from the Opposite Party, {opposite_party}, through an online platform.
2. {facts}
3. The consideration paid for the goods/services is Rs. {value}.
4. Despite repeated requests, the Opposite Party has failed to deliver, replace or refund, and has not redressed the grievance.

GROUNDS:
{grounds}

""" + _RELIEF.replace("{relief_main}", "direct the Opposite Party to refund Rs. {value} with interest at 9% per annum from the date of payment, or replace the goods with defect-free goods") + "\n\n" + _VERIFICATION),
    ("banking", """FACTS OF THE CASE:
1. The Complainant, {complainant}, is a customer of the Opposite Party, {opposite_party}, and has availed its banking/financial services for consideration, and is therefore a consumer under Section 2(7) of the Consumer Protection Act, 2019.
2. {facts}
3. The amount involved is Rs. {value}.
4. The Complainant approached the Opposite Party and its grievance cell, but the grievance remains unresolved.

GROUNDS:
{grounds}

""" + _RELIEF.replace("{relief_main}", "direct the Opposite Party to reverse/refund Rs. {value} with interest at the applicable rate from the date of debit and to correct the Complainant's account records") + "\n\n" + _VERIFICATION),
    ("other", """FACTS OF THE CASE:
1. The Complainant, {complainant}, is a consumer within the meaning of Section 2(7) of the Consumer Protection Act, 2019, having availed goods/services from the Opposite Party, {opposite_party}, for consideration.
2. {facts}
3. The value of the goods/services paid as consideration is Rs. {value}.
4. The Opposite Party has failed to redress the grievance despite requests.

GROUNDS:
{grounds}

""" + _RELIEF.replace("{relief_main}", "direct the Opposite Party to refund Rs. {value} with interest, or to remove the defect/deficiency complained of") + "\n\n" + _VERIFICATION),
]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql: str, params=()) -> list[dict]:
    with transaction() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def query_one(sql: str, params=()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=()) -> int:
    with transaction() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def init_db() -> None:
    config.ensure_dirs()
    with transaction() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM users WHERE email=?", (config.SEED_ADMIN_EMAIL,)).fetchone():
            pw = bcrypt.hashpw(config.SEED_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
            c.execute("INSERT INTO users(name,email,pw_hash,role,active) VALUES(?,?,?,?,1)",
                      ("Administrator", config.SEED_ADMIN_EMAIL, pw, "admin"))
            log.info("Seeded admin user")
        if not c.execute("SELECT 1 FROM templates LIMIT 1").fetchone():
            c.executemany("INSERT INTO templates(category,body) VALUES(?,?)", SEED_TEMPLATES)
            log.info("Seeded %d templates", len(SEED_TEMPLATES))


# ---------- users ----------
def create_user(name: str, email: str, pw_hash: str, role: str = "consumer") -> int:
    return execute("INSERT INTO users(name,email,pw_hash,role,active) VALUES(?,?,?,?,1)",
                   (name, email, pw_hash, role))


def get_user_by_email(email: str) -> dict | None:
    return query_one("SELECT * FROM users WHERE email=?", (email,))


def get_user(user_id: int) -> dict | None:
    return query_one("SELECT * FROM users WHERE id=?", (user_id,))


def list_users() -> list[dict]:
    return query("SELECT id,name,email,role,active FROM users ORDER BY id")


def set_user_active(user_id: int, active: bool) -> None:
    execute("UPDATE users SET active=? WHERE id=?", (1 if active else 0, user_id))


def set_user_role(user_id: int, role: str) -> None:
    if role not in config.ROLES:
        raise ValueError(f"Invalid role: {role}")
    execute("UPDATE users SET role=? WHERE id=?", (role, user_id))


# ---------- cases ----------
_CASE_FIELDS = {"text", "value", "state", "district", "category", "forum", "opposite_party",
                "draft", "status", "admin_note", "pdf_path"}


def create_case(user_id: int, text: str, value: float, state: str, district: str,
                category: str, forum: str, opposite_party: str = "") -> int:
    return execute(
        "INSERT INTO cases(user_id,text,value,state,district,category,forum,opposite_party,status,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,'submitted',?)",
        (user_id, text, value, state, district, category, forum, opposite_party, now()))


def update_case(case_id: int, **fields) -> None:
    bad = set(fields) - _CASE_FIELDS
    if bad:
        raise ValueError(f"Unknown case fields: {bad}")
    if "status" in fields and fields["status"] not in config.STATUSES:
        raise ValueError(f"Invalid status: {fields['status']}")
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)  # keys are whitelisted above
    execute(f"UPDATE cases SET {cols} WHERE id=?", (*fields.values(), case_id))


def get_case(case_id: int) -> dict | None:
    return query_one("SELECT c.*, u.name AS user_name, u.email AS user_email FROM cases c "
                     "JOIN users u ON u.id=c.user_id WHERE c.id=?", (case_id,))


def list_cases(user_id: int | None = None, status: str | None = None) -> list[dict]:
    sql = ("SELECT c.*, u.name AS user_name, u.email AS user_email FROM cases c "
           "JOIN users u ON u.id=c.user_id WHERE 1=1")
    params: list = []
    if user_id is not None:
        sql += " AND c.user_id=?"
        params.append(user_id)
    if status:
        sql += " AND c.status=?"
        params.append(status)
    return query(sql + " ORDER BY c.id DESC", params)


# ---------- templates ----------
def list_templates() -> list[dict]:
    return query("SELECT * FROM templates ORDER BY category, id")


def get_template_for_category(category: str) -> dict | None:
    return (query_one("SELECT * FROM templates WHERE category=? ORDER BY id LIMIT 1", (category,))
            or query_one("SELECT * FROM templates WHERE category='other' ORDER BY id LIMIT 1")
            or query_one("SELECT * FROM templates ORDER BY id LIMIT 1"))


def create_template(category: str, body: str) -> int:
    return execute("INSERT INTO templates(category,body) VALUES(?,?)", (category, body))


def update_template(tid: int, category: str, body: str) -> None:
    execute("UPDATE templates SET category=?, body=? WHERE id=?", (category, body, tid))


def delete_template(tid: int) -> None:
    execute("DELETE FROM templates WHERE id=?", (tid,))


# ---------- notifications ----------
def add_notification(user_id: int, msg: str) -> int:
    return execute("INSERT INTO notifications(user_id,msg,read,created_at) VALUES(?,?,0,?)",
                   (user_id, msg, now()))


def list_notifications(user_id: int) -> list[dict]:
    return query("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC", (user_id,))


def unread_count(user_id: int) -> int:
    row = query_one("SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND read=0", (user_id,))
    return row["n"] if row else 0


def mark_all_read(user_id: int) -> None:
    execute("UPDATE notifications SET read=1 WHERE user_id=? AND read=0", (user_id,))


# ---------- knowledge base ----------
def add_chunks(rows: list[tuple[str, str, str, bytes | None]]) -> None:
    with transaction() as c:
        c.executemany("INSERT INTO kb_chunks(source,category,text,embedding) VALUES(?,?,?,?)", rows)


def all_chunks() -> list[dict]:
    return query("SELECT id,source,category,text,embedding FROM kb_chunks")


def chunks_missing_embedding() -> list[dict]:
    return query("SELECT id,text FROM kb_chunks WHERE embedding IS NULL")


def set_chunk_embedding(chunk_id: int, emb: bytes) -> None:
    execute("UPDATE kb_chunks SET embedding=? WHERE id=?", (emb, chunk_id))


def chunk_count() -> int:
    return query_one("SELECT COUNT(*) AS n FROM kb_chunks")["n"]


def kb_stats() -> dict:
    total = chunk_count()
    embedded = query_one("SELECT COUNT(*) AS n FROM kb_chunks WHERE embedding IS NOT NULL")["n"]
    by_source = query("SELECT source, category, COUNT(*) AS n FROM kb_chunks GROUP BY source, category ORDER BY source")
    return {"total": total, "embedded": embedded, "by_source": by_source}
