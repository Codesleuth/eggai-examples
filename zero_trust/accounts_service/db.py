import logging
import sqlite3

logger = logging.getLogger("db")

_db: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = sqlite3.connect(":memory:", check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _seed(_db)
        logger.info("In-memory SQLite seeded: 5 accounts, transactions for alice and bob")
    return _db


def _seed(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE accounts (
            account_id  TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            owner       TEXT NOT NULL
        );
        CREATE TABLE transactions (
            id          TEXT PRIMARY KEY,
            account_id  TEXT NOT NULL REFERENCES accounts(account_id),
            amount      REAL NOT NULL,
            merchant    TEXT NOT NULL,
            date        TEXT NOT NULL,
            category    TEXT NOT NULL
        );
    """)

    db.executemany(
        "INSERT INTO accounts VALUES (?,?,?)",
        [
            # Alice
            ("ACC-001", "Current Account", "alice"),
            ("ACC-002", "Savings",         "alice"),
            ("ACC-003", "Cash ISA",        "alice"),
            # Bob
            ("ACC-004", "Current Account", "bob"),
            ("ACC-005", "Savings",         "bob"),
        ],
    )

    db.executemany(
        "INSERT INTO transactions VALUES (?,?,?,?,?,?)",
        [
            # Alice — Current Account (ACC-001)
            ("txn-a001", "ACC-001",   4.50, "Coffee Shop",       "2026-03-01", "Food & Drink"),
            ("txn-a002", "ACC-001",  54.20, "Grocery Mart",      "2026-03-03", "Groceries"),
            ("txn-a003", "ACC-001",  45.50, "Gas Station",       "2026-03-05", "Transportation"),
            ("txn-a004", "ACC-001",  12.99, "Streaming Service", "2026-03-05", "Entertainment"),
            ("txn-a005", "ACC-001",   8.75, "Coffee Shop",       "2026-03-07", "Food & Drink"),
            ("txn-a006", "ACC-001",  34.00, "Pharmacy",          "2026-03-09", "Health"),
            ("txn-a007", "ACC-001",  62.40, "Grocery Mart",      "2026-03-11", "Groceries"),
            ("txn-a008", "ACC-001",  18.50, "Restaurant",        "2026-03-12", "Food & Drink"),
            ("txn-a009", "ACC-001",   9.99, "Music Streaming",   "2026-03-14", "Entertainment"),
            ("txn-a010", "ACC-001",  44.00, "Gas Station",       "2026-03-15", "Transportation"),
            ("txn-a011", "ACC-001", 150.00, "Department Store",  "2026-03-16", "Shopping"),
            ("txn-a012", "ACC-001",  29.99, "Book Store",        "2026-03-17", "Shopping"),
            ("txn-a013", "ACC-001",  75.00, "Gym Membership",    "2026-03-18", "Health"),
            ("txn-a014", "ACC-001",  58.30, "Grocery Mart",      "2026-03-19", "Groceries"),
            ("txn-a015", "ACC-001",  22.00, "Restaurant",        "2026-03-20", "Food & Drink"),
            # Alice — Savings (ACC-002)
            ("txn-a016", "ACC-002", 500.00, "Salary Transfer",   "2026-03-01", "Transfer"),
            ("txn-a017", "ACC-002", 200.00, "Salary Transfer",   "2026-03-15", "Transfer"),
            ("txn-a018", "ACC-002",  85.00, "Interest Payment",  "2026-03-31", "Interest"),
            # Alice — Cash ISA (ACC-003)
            ("txn-a019", "ACC-003", 1000.00, "ISA Deposit",      "2026-03-01", "Investment"),
            ("txn-a020", "ACC-003",   42.50, "ISA Interest",     "2026-03-31", "Interest"),
            # Bob — Current Account (ACC-004)
            ("txn-b001", "ACC-004",  22.00, "Restaurant",        "2026-03-01", "Food & Drink"),
            ("txn-b002", "ACC-004",  14.99, "Streaming Service", "2026-03-02", "Entertainment"),
            ("txn-b003", "ACC-004",   5.25, "Coffee Shop",       "2026-03-04", "Food & Drink"),
            ("txn-b004", "ACC-004",  89.99, "Clothing Store",    "2026-03-04", "Shopping"),
            ("txn-b005", "ACC-004",  46.00, "Gas Station",       "2026-03-06", "Transportation"),
            ("txn-b006", "ACC-004",  12.50, "Pharmacy",          "2026-03-07", "Health"),
            ("txn-b007", "ACC-004",  67.10, "Grocery Mart",      "2026-03-08", "Groceries"),
            ("txn-b008", "ACC-004",  35.00, "Restaurant",        "2026-03-09", "Food & Drink"),
            ("txn-b009", "ACC-004", 199.00, "Electronics Store", "2026-03-11", "Shopping"),
            ("txn-b010", "ACC-004",   6.00, "Coffee Shop",       "2026-03-12", "Food & Drink"),
            ("txn-b011", "ACC-004",   9.99, "Music Streaming",   "2026-03-13", "Entertainment"),
            ("txn-b012", "ACC-004",  48.75, "Gas Station",       "2026-03-14", "Transportation"),
            ("txn-b013", "ACC-004",  89.00, "Grocery Mart",      "2026-03-16", "Groceries"),
            ("txn-b014", "ACC-004",  27.50, "Restaurant",        "2026-03-17", "Food & Drink"),
            ("txn-b015", "ACC-004",  49.99, "Clothing Store",    "2026-03-19", "Shopping"),
            # Bob — Savings (ACC-005)
            ("txn-b016", "ACC-005", 750.00, "Salary Transfer",   "2026-03-01", "Transfer"),
            ("txn-b017", "ACC-005", 300.00, "Salary Transfer",   "2026-03-15", "Transfer"),
            ("txn-b018", "ACC-005",  62.00, "Interest Payment",  "2026-03-31", "Interest"),
        ],
    )
    db.commit()
