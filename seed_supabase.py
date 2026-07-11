"""
seed_supabase.py — Run this ONCE to create tables + seed data in your Supabase PostgreSQL DB.
Requires SUPABASE_DB_URL in .env.

Usage:
    python seed_supabase.py
"""
import os, psycopg2
from dotenv import load_dotenv

load_dotenv()
URL = os.getenv("SUPABASE_DB_URL")
if not URL:
    raise SystemExit("SUPABASE_DB_URL not set in .env")

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscription_tier (
    subscription_tier_id  SERIAL PRIMARY KEY,
    tier_name             TEXT NOT NULL,
    total_credits         INTEGER NOT NULL DEFAULT 500
);
CREATE TABLE IF NOT EXISTS subscription_tier_log (
    subscription_tier_log_id SERIAL PRIMARY KEY,
    subscription_tier_id  INTEGER NOT NULL REFERENCES subscription_tier(subscription_tier_id),
    action                TEXT NOT NULL,
    details               TEXT,
    created_date          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS features (
    feature_id    SERIAL PRIMARY KEY,
    feature_name  TEXT NOT NULL,
    description   TEXT,
    active_flag   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS features_log (
    feature_log_id  SERIAL PRIMARY KEY,
    feature_id      INTEGER NOT NULL REFERENCES features(feature_id),
    action          TEXT NOT NULL,
    details         TEXT,
    created_date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tier_feature_mapping (
    mapping_pk            SERIAL PRIMARY KEY,
    subscription_tier_id  INTEGER NOT NULL REFERENCES subscription_tier(subscription_tier_id),
    feature_id            INTEGER NOT NULL REFERENCES features(feature_id),
    capability_included   INTEGER NOT NULL DEFAULT 0,
    credit_per_click_tier INTEGER NOT NULL DEFAULT 0,
    file_limit            INTEGER NOT NULL DEFAULT 0,
    UNIQUE(subscription_tier_id, feature_id)
);
CREATE TABLE IF NOT EXISTS tier_feature_mapping_log (
    mapping_log_id  SERIAL PRIMARY KEY,
    mapping_pk      INTEGER NOT NULL REFERENCES tier_feature_mapping(mapping_pk),
    action          TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    created_date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS account (
    account_id            SERIAL PRIMARY KEY,
    account_name          TEXT NOT NULL,
    subscription_tier_id  INTEGER REFERENCES subscription_tier(subscription_tier_id),
    active_account        INTEGER NOT NULL DEFAULT 1,
    start_date            TEXT,
    end_date              TEXT,
    created_by            TEXT DEFAULT 'system',
    created_date          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_by           TEXT DEFAULT 'system',
    modified_date         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS account_plan (
    account_plan_id       SERIAL PRIMARY KEY,
    account_id            INTEGER NOT NULL REFERENCES account(account_id),
    subscription_tier_id  INTEGER NOT NULL REFERENCES subscription_tier(subscription_tier_id),
    start_date            TEXT NOT NULL,
    end_date              TEXT,
    created_by            TEXT DEFAULT 'system',
    created_date          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_by           TEXT DEFAULT 'system',
    modified_date         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS account_log (
    account_log_id        SERIAL PRIMARY KEY,
    account_id            INTEGER NOT NULL REFERENCES account(account_id),
    subscription_tier_id  INTEGER REFERENCES subscription_tier(subscription_tier_id),
    old_tier_id           INTEGER REFERENCES subscription_tier(subscription_tier_id),
    description           TEXT,
    start_date            TEXT,
    end_date              TEXT,
    created_by            TEXT DEFAULT 'system',
    created_date          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_by           TEXT DEFAULT 'system',
    modified_date         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "user" (
    user_pk       SERIAL PRIMARY KEY,
    account_id    INTEGER NOT NULL REFERENCES account(account_id),
    user_id       TEXT,
    active_user   INTEGER NOT NULL DEFAULT 1,
    user_email    TEXT NOT NULL,
    created_by    TEXT DEFAULT 'system',
    created_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_by   TEXT DEFAULT 'system',
    modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(account_id, user_email)
);
CREATE TABLE IF NOT EXISTS user_log (
    user_log_id   SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES "user"(user_pk),
    account_id    INTEGER NOT NULL,
    action        TEXT NOT NULL,
    details       TEXT,
    created_by    TEXT DEFAULT 'system',
    created_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS usage_log (
    usage_log_id          SERIAL PRIMARY KEY,
    user_id               INTEGER NOT NULL REFERENCES "user"(user_pk),
    account_id            INTEGER NOT NULL REFERENCES account(account_id),
    feature_id            INTEGER NOT NULL REFERENCES features(feature_id),
    subscription_tier_id  INTEGER NOT NULL REFERENCES subscription_tier(subscription_tier_id),
    account_plan_id       INTEGER NOT NULL REFERENCES account_plan(account_plan_id),
    success_indicator     INTEGER NOT NULL DEFAULT 1,
    no_of_files           INTEGER DEFAULT 0,
    usage_timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SEED = [
    # tiers
    "INSERT INTO subscription_tier (tier_name, total_credits) VALUES ('Starter', 500) ON CONFLICT DO NOTHING",
    "INSERT INTO subscription_tier (tier_name, total_credits) VALUES ('Pro', 2000) ON CONFLICT DO NOTHING",
    "INSERT INTO subscription_tier (tier_name, total_credits) VALUES ('Enterprise', 10000) ON CONFLICT DO NOTHING",
    # features
    "INSERT INTO features (feature_name, description) VALUES ('OCR', 'Optical character recognition') ON CONFLICT DO NOTHING",
    "INSERT INTO features (feature_name, description) VALUES ('Translation', 'Document translation') ON CONFLICT DO NOTHING",
    "INSERT INTO features (feature_name, description) VALUES ('Analytics', 'Usage analytics') ON CONFLICT DO NOTHING",
]

conn = psycopg2.connect(URL)
cur  = conn.cursor()
cur.execute(SCHEMA)
for s in SEED:
    cur.execute(s)

# accounts + users
accounts = [
    ("Acme Corp",       "Pro",        "2025-01-01", "2025-12-31", [("alice@acme.com","AC-0001"),("bob@acme.com","AC-0002"),("carol@acme.com","AC-0003")]),
    ("Beta Ltd",        "Starter",    "2025-03-01", "2025-12-31", [("dave@beta.com","BL-0001"),("eve@beta.com","BL-0002")]),
    ("Gamma Inc",       "Enterprise", "2025-01-01", "2025-12-31", [("frank@gamma.com","GI-0001"),("grace@gamma.com","GI-0002")]),
    ("Delta Solutions", "Pro",        "2025-06-01", "2025-12-31", [("jack@delta.com","DS-0001")]),
    ("Echo Partners",   "Starter",    "2025-02-01", "2025-12-31", [("kate@echo.com","EP-0001"),("leo@echo.com","EP-0002")]),
]

for acct_name, tier_name, start, end, users in accounts:
    cur.execute("SELECT subscription_tier_id FROM subscription_tier WHERE tier_name=%s", (tier_name,))
    tid = cur.fetchone()[0]
    cur.execute("INSERT INTO account (account_name, subscription_tier_id, active_account, start_date, end_date) VALUES (%s,%s,1,%s,%s) RETURNING account_id",
                (acct_name, tid, start, end))
    aid = cur.fetchone()[0]
    cur.execute("INSERT INTO account_plan (account_id, subscription_tier_id, start_date, end_date) VALUES (%s,%s,%s,%s) RETURNING account_plan_id",
                (aid, tid, start, end))
    plan_id = cur.fetchone()[0]
    cur.execute("INSERT INTO account_log (account_id, subscription_tier_id, description, start_date, end_date) VALUES (%s,%s,%s,%s,%s)",
                (aid, tid, f"Account '{acct_name}' created", start, end))
    cur.execute("SELECT feature_id FROM features LIMIT 1")
    fid = cur.fetchone()[0]
    for email, uid_str in users:
        cur.execute('INSERT INTO "user" (account_id, user_email, user_id, active_user) VALUES (%s,%s,%s,1) ON CONFLICT DO NOTHING RETURNING user_pk',
                    (aid, email, uid_str))
        row = cur.fetchone()
        if row:
            upk = row[0]
            cur.execute("INSERT INTO user_log (user_id, account_id, action, details) VALUES (%s,%s,%s,%s)",
                        (upk, aid, "member_added", f"{email} added"))
            cur.execute("INSERT INTO usage_log (user_id, account_id, feature_id, subscription_tier_id, account_plan_id, success_indicator, no_of_files) VALUES (%s,%s,%s,%s,%s,1,%s)",
                        (upk, aid, fid, tid, plan_id, 3))

conn.commit()
cur.close()
conn.close()
print("✅ Supabase seeded successfully.")
