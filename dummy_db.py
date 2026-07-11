"""
dummy_db.py — Creates admin_dummy.db with simple, readable seed data.
Run once: python dummy_db.py
Used as fallback when Supabase is unavailable (USE_DUMMY=true in .env).
"""
import sqlite3, os

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscription_tier (
    subscription_tier_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    tier_name             TEXT NOT NULL,
    total_credits         INTEGER NOT NULL DEFAULT 500
);
CREATE TABLE IF NOT EXISTS subscription_tier_log (
    subscription_tier_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_tier_id  INTEGER NOT NULL REFERENCES subscription_tier(subscription_tier_id),
    action                TEXT NOT NULL,
    details               TEXT,
    created_date          TEXT DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS features (
    feature_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_name  TEXT NOT NULL,
    description   TEXT,
    active_flag   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS features_log (
    feature_log_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_id      INTEGER NOT NULL REFERENCES features(feature_id),
    action          TEXT NOT NULL,
    details         TEXT,
    created_date    TEXT DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS tier_feature_mapping (
    mapping_pk            INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_tier_id  INTEGER NOT NULL REFERENCES subscription_tier(subscription_tier_id),
    feature_id            INTEGER NOT NULL REFERENCES features(feature_id),
    capability_included   INTEGER NOT NULL DEFAULT 0,
    credit_per_click_tier INTEGER NOT NULL DEFAULT 0,
    file_limit            INTEGER NOT NULL DEFAULT 0,
    UNIQUE(subscription_tier_id, feature_id)
);
CREATE TABLE IF NOT EXISTS tier_feature_mapping_log (
    mapping_log_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    mapping_pk      INTEGER NOT NULL REFERENCES tier_feature_mapping(mapping_pk),
    action          TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    created_date    TEXT DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS account (
    account_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name          TEXT NOT NULL,
    subscription_tier_id  INTEGER REFERENCES subscription_tier(subscription_tier_id),
    active_account        INTEGER NOT NULL DEFAULT 1,
    start_date            TEXT,
    end_date              TEXT,
    created_by            TEXT DEFAULT 'system',
    created_date          TEXT DEFAULT (CURRENT_TIMESTAMP),
    modified_by           TEXT DEFAULT 'system',
    modified_date         TEXT DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS account_plan (
    account_plan_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id            INTEGER NOT NULL REFERENCES account(account_id),
    subscription_tier_id  INTEGER NOT NULL REFERENCES subscription_tier(subscription_tier_id),
    start_date            TEXT NOT NULL,
    end_date              TEXT,
    created_by            TEXT DEFAULT 'system',
    created_date          TEXT DEFAULT (CURRENT_TIMESTAMP),
    modified_by           TEXT DEFAULT 'system',
    modified_date         TEXT DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS account_log (
    account_log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id            INTEGER NOT NULL REFERENCES account(account_id),
    subscription_tier_id  INTEGER REFERENCES subscription_tier(subscription_tier_id),
    old_tier_id           INTEGER REFERENCES subscription_tier(subscription_tier_id),
    description           TEXT,
    start_date            TEXT,
    end_date              TEXT,
    created_by            TEXT DEFAULT 'system',
    created_date          TEXT DEFAULT (CURRENT_TIMESTAMP),
    modified_by           TEXT DEFAULT 'system',
    modified_date         TEXT DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS "user" (
    user_pk       INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL REFERENCES account(account_id),
    user_id       TEXT,
    active_user   INTEGER NOT NULL DEFAULT 1,
    user_email    TEXT NOT NULL,
    created_by    TEXT DEFAULT 'system',
    created_date  TEXT DEFAULT (CURRENT_TIMESTAMP),
    modified_by   TEXT DEFAULT 'system',
    modified_date TEXT DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE(account_id, user_email)
);
CREATE TABLE IF NOT EXISTS user_log (
    user_log_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES "user"(user_pk),
    account_id    INTEGER NOT NULL,
    action        TEXT NOT NULL,
    details       TEXT,
    created_by    TEXT DEFAULT 'system',
    created_date  TEXT DEFAULT (CURRENT_TIMESTAMP)
);
CREATE TABLE IF NOT EXISTS usage_log (
    usage_log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id               INTEGER NOT NULL REFERENCES "user"(user_pk),
    account_id            INTEGER NOT NULL REFERENCES account(account_id),
    feature_id            INTEGER NOT NULL REFERENCES features(feature_id),
    subscription_tier_id  INTEGER NOT NULL REFERENCES subscription_tier(subscription_tier_id),
    account_plan_id       INTEGER NOT NULL REFERENCES account_plan(account_plan_id),
    success_indicator     INTEGER NOT NULL DEFAULT 1,
    no_of_files           INTEGER DEFAULT 0,
    usage_timestamp       TEXT DEFAULT (CURRENT_TIMESTAMP)
);
"""

DB_PATH = "admin_dummy.db"

def build():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()
    c.executescript(SCHEMA)

    # ── Tiers ─────────────────────────────────────────────────────────────────
    tiers = [("Starter", 500), ("Pro", 2000), ("Enterprise", 10000)]
    tier_ids = {}
    for name, credits in tiers:
        c.execute("INSERT INTO subscription_tier (tier_name, total_credits) VALUES (?,?)", (name, credits))
        tid = c.lastrowid
        tier_ids[name] = tid
        c.execute("INSERT INTO subscription_tier_log (subscription_tier_id, action, details) VALUES (?,?,?)",
                  (tid, "created", f"Tier '{name}' with {credits} credits"))

    # ── Features ──────────────────────────────────────────────────────────────
    features = [("OCR", "Optical character recognition"), ("Translation", "Document translation"), ("Analytics", "Usage analytics")]
    feat_ids = {}
    for fname, fdesc in features:
        c.execute("INSERT INTO features (feature_name, description) VALUES (?,?)", (fname, fdesc))
        fid = c.lastrowid
        feat_ids[fname] = fid
        c.execute("INSERT INTO features_log (feature_id, action, details) VALUES (?,?,?)",
                  (fid, "created", f"Feature '{fname}' added"))

    # ── Tier-Feature Mappings ─────────────────────────────────────────────────
    for rank, (tname, tid) in enumerate(tier_ids.items()):
        for fname, fid in feat_ids.items():
            cpu = rank * 2 + 1
            fl  = (rank + 1) * 10
            c.execute("INSERT INTO tier_feature_mapping (subscription_tier_id, feature_id, capability_included, credit_per_click_tier, file_limit) VALUES (?,?,1,?,?)",
                      (tid, fid, cpu, fl))
            mpk = c.lastrowid
            c.execute("INSERT INTO tier_feature_mapping_log (mapping_pk, action, new_value) VALUES (?,?,?)",
                      (mpk, "created", f"cpu={cpu},fl={fl}"))

    # ── Accounts ──────────────────────────────────────────────────────────────
    accounts = [
        ("Acme Corp",        "Pro",        "2025-01-01", "2025-12-31",
         [("alice@acme.com","AC-0001"),("bob@acme.com","AC-0002"),("carol@acme.com","AC-0003")]),
        ("Beta Ltd",         "Starter",    "2025-03-01", "2025-12-31",
         [("dave@beta.com","BL-0001"),("eve@beta.com","BL-0002")]),
        ("Gamma Inc",        "Enterprise", "2025-01-01", "2025-12-31",
         [("frank@gamma.com","GI-0001"),("grace@gamma.com","GI-0002"),("henry@gamma.com","GI-0003"),("ida@gamma.com","GI-0004")]),
        ("Delta Solutions",  "Pro",        "2025-06-01", "2025-12-31",
         [("jack@delta.com","DS-0001")]),
        ("Echo Partners",    "Starter",    "2025-02-01", "2025-12-31",
         [("kate@echo.com","EP-0001"),("leo@echo.com","EP-0002")]),
    ]

    for acct_name, tier_name, start, end, users in accounts:
        tid = tier_ids[tier_name]
        c.execute("INSERT INTO account (account_name, subscription_tier_id, active_account, start_date, end_date) VALUES (?,?,1,?,?)",
                  (acct_name, tid, start, end))
        aid = c.lastrowid
        c.execute("INSERT INTO account_plan (account_id, subscription_tier_id, start_date, end_date) VALUES (?,?,?,?)",
                  (aid, tid, start, end))
        plan_id = c.lastrowid
        c.execute("INSERT INTO account_log (account_id, subscription_tier_id, description, start_date, end_date) VALUES (?,?,?,?,?)",
                  (aid, tid, f"Account '{acct_name}' created on {start}", start, end))

        for email, uid_str in users:
            c.execute('INSERT INTO "user" (account_id, user_email, user_id, active_user) VALUES (?,?,?,1)',
                      (aid, email, uid_str))
            upk = c.lastrowid
            c.execute("INSERT INTO user_log (user_id, account_id, action, details) VALUES (?,?,?,?)",
                      (upk, aid, "member_added", f"{email} added as {uid_str}"))

            # one sample usage per user
            fid = list(feat_ids.values())[upk % len(feat_ids)]
            c.execute("INSERT INTO usage_log (user_id, account_id, feature_id, subscription_tier_id, account_plan_id, success_indicator, no_of_files) VALUES (?,?,?,?,?,1,?)",
                      (upk, aid, fid, tid, plan_id, upk % 10 + 1))

    conn.commit()
    conn.close()
    print(f"✅  {DB_PATH} created with {len(accounts)} accounts, tiers={list(tier_ids)}, features={list(feat_ids)}")

if __name__ == "__main__":
    build()
