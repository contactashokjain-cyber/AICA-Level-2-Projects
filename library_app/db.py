from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
INSERT INTO schema_version(version) SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version);
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 password_salt TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('ADMIN','LIBRARIAN')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS members(
 id INTEGER PRIMARY KEY, member_id TEXT NOT NULL UNIQUE, sno INTEGER, name TEXT NOT NULL,
 father_name TEXT, address TEXT, registration_no TEXT UNIQUE, mobile TEXT, registration_date TEXT,
 status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE','SUSPENDED')),
 remarks TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS books(
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT, publisher TEXT, edition TEXT, isbn TEXT,
 language TEXT, page_count INTEGER CHECK(page_count IS NULL OR page_count >= 0), category TEXT,
 publication_year INTEGER, cover_path TEXT, acquisition_date TEXT, source TEXT, cost REAL CHECK(cost IS NULL OR cost >= 0),
 remarks TEXT, archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_isbn ON books(isbn);
CREATE TABLE IF NOT EXISTS locations(
 id INTEGER PRIMARY KEY, rack TEXT NOT NULL, shelf TEXT NOT NULL DEFAULT '', compartment TEXT NOT NULL DEFAULT '',
 UNIQUE(rack,shelf,compartment)
);
CREATE TABLE IF NOT EXISTS book_copies(
 id INTEGER PRIMARY KEY, accession_no TEXT NOT NULL UNIQUE, book_id INTEGER NOT NULL REFERENCES books(id),
 location_id INTEGER REFERENCES locations(id), status TEXT NOT NULL DEFAULT 'AVAILABLE'
 CHECK(status IN ('AVAILABLE','ISSUED','LOST','DAMAGED','WITHDRAWN')), remarks TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_copies_book_status ON book_copies(book_id,status);
CREATE TABLE IF NOT EXISTS loans(
 id INTEGER PRIMARY KEY, copy_id INTEGER NOT NULL REFERENCES book_copies(id), member_id INTEGER NOT NULL REFERENCES members(id),
 issued_by INTEGER NOT NULL REFERENCES users(id), returned_to INTEGER REFERENCES users(id),
 issue_date TEXT NOT NULL, due_date TEXT NOT NULL, return_date TEXT,
 loan_days INTEGER NOT NULL CHECK(loan_days IN (7,15,21,28)), status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','RETURNED','LOST')),
 notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_loan_per_copy ON loans(copy_id) WHERE status='ACTIVE';
CREATE INDEX IF NOT EXISTS idx_loans_due_status ON loans(status,due_date);
CREATE TABLE IF NOT EXISTS reservations(
 id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id), member_id INTEGER NOT NULL REFERENCES members(id),
 requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT 'WAITING'
 CHECK(status IN ('WAITING','NOTIFIED','FULFILLED','CANCELLED')), notified_at TEXT, fulfilled_at TEXT,
 UNIQUE(book_id,member_id,status)
);
CREATE INDEX IF NOT EXISTS idx_reservation_queue ON reservations(book_id,status,requested_at,id);
CREATE TABLE IF NOT EXISTS penalty_rules(
 id INTEGER PRIMARY KEY, rate_per_day REAL NOT NULL CHECK(rate_per_day >= 0), effective_from TEXT NOT NULL,
 grace_days INTEGER NOT NULL DEFAULT 0 CHECK(grace_days >= 0), max_penalty REAL CHECK(max_penalty IS NULL OR max_penalty >= 0),
 count_partial_day INTEGER NOT NULL DEFAULT 0 CHECK(count_partial_day IN (0,1)), notes TEXT, created_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS penalty_assessments(
 id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL UNIQUE REFERENCES loans(id), overdue_days INTEGER NOT NULL,
 amount REAL NOT NULL CHECK(amount >= 0), assessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, waived_amount REAL NOT NULL DEFAULT 0,
 notes TEXT
);
CREATE TABLE IF NOT EXISTS penalty_payments(
 id INTEGER PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(id), amount REAL NOT NULL CHECK(amount > 0),
 payment_date TEXT NOT NULL, received_by INTEGER NOT NULL REFERENCES users(id), receipt_no TEXT UNIQUE, notes TEXT
);
CREATE TABLE IF NOT EXISTS payment_allocations(
 id INTEGER PRIMARY KEY, payment_id INTEGER NOT NULL REFERENCES penalty_payments(id), assessment_id INTEGER NOT NULL REFERENCES penalty_assessments(id),
 amount REAL NOT NULL CHECK(amount > 0), UNIQUE(payment_id,assessment_id)
);
CREATE TABLE IF NOT EXISTS audit_log(
 id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), action TEXT NOT NULL, entity_type TEXT NOT NULL,
 entity_id TEXT, details TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
'''

class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=15000')
        return conn

    def initialize(self):
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def transaction(self):
        return self.connect()
