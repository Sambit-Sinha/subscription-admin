# Subscription Admin Agent

A chat-based admin interface for managing subscription database records.
Type a natural language instruction → the agent plans the SQL → you review and confirm → changes execute.

---

## What it does

- Deactivate / reactivate users or accounts
- Add single or multiple users to an account
- Change an account's subscription tier
- Add, disable, or update features and tier-feature mappings
- Update credit limits for a tier
- Every change automatically writes the corresponding audit log row
- Full SQL preview before anything is executed — you always confirm first
- Browse any table directly from the sidebar

---

## Prerequisites

- Python 3.9 or higher
- A free Google Gemini API key — get one at https://aistudio.google.com/app/apikey (1 500 free requests/day)
- (Optional) A Supabase PostgreSQL URL for a persistent cloud database

---

## Running locally — step by step

### 1. Clone the repo

```bash
git clone https://github.com/Sambit-Sinha/subscription-admin.git
cd subscription-admin
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Mac / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your `.env` file

```bash
cp .env.example .env
```

Fill in at minimum your Gemini API key (see the switching guide below for the database options).

### 5. Run the app

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501**. The sidebar shows a green dot for Supabase or a yellow dot for SQLite so you always know which database is active.

---

## Switching between Supabase and the dummy database

The app decides which database to use based on a single line in your `.env` file — `SUPABASE_DB_URL`. No code changes needed, ever.

---

### Option A — Use Supabase (PostgreSQL, cloud, persistent)

**When to use:** normal day-to-day use. Changes are saved permanently in the cloud and accessible from any machine.

**How to switch ON:**

Open `.env` and make sure `SUPABASE_DB_URL` is present and uncommented:

```env
GEMINI_API_KEY=your_gemini_key
SUPABASE_DB_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres
DUMMY_DB_PATH=admin_dummy.db
```

If you are setting up Supabase for the first time, run the seeder once to create the tables and load sample data:

```bash
python seed_supabase.py
```

You only need to run this once. After that, just start the app normally.

**Restart the app** after editing `.env`:

```bash
# Stop with Ctrl+C, then:
streamlit run app.py
```

The sidebar will show: 🟢 `Supabase (PostgreSQL)`

---

### Option B — Use the dummy database (SQLite, local, offline)

**When to use:** when Supabase is down, you have no internet, or you want to test something without touching real data.

**How to switch ON:**

Open `.env` and comment out (or delete) the `SUPABASE_DB_URL` line by adding a `#` at the start:

```env
GEMINI_API_KEY=your_gemini_key
# SUPABASE_DB_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres
DUMMY_DB_PATH=admin_dummy.db
```

**Restart the app:**

```bash
# Stop with Ctrl+C, then:
streamlit run app.py
```

The sidebar will show: 🟡 `SQLite fallback (admin_dummy.db)`

The dummy database file (`admin_dummy.db`) is created automatically if it does not exist. It comes pre-loaded with 5 sample accounts — see the sample data section below.

> **Note:** The dummy database is a local file on your machine. It is not shared between machines and is not backed up. Treat it as a scratch pad for testing only.

---

### Quick reference

| | Supabase | Dummy DB |
|---|---|---|
| `.env` setting | `SUPABASE_DB_URL=postgresql://...` | Comment out or remove `SUPABASE_DB_URL` |
| Sidebar indicator | 🟢 `Supabase (PostgreSQL)` | 🟡 `SQLite fallback (admin_dummy.db)` |
| Data persists? | Yes — cloud storage | Yes — local file, but only on this machine |
| Works offline? | No | Yes |
| Shared across machines? | Yes | No |
| Safe for testing? | Be careful — changes are real | Yes — isolated scratch pad |

---

### Troubleshooting Supabase connection issues

If the app starts but the sidebar shows yellow (SQLite) when you expected green (Supabase), check:

1. **Is `SUPABASE_DB_URL` set in `.env`?** Open `.env` and confirm the line is present and not commented out.
2. **Did you restart the app after editing `.env`?** Streamlit does not reload environment variables on hot-reload. Stop (`Ctrl+C`) and start again.
3. **Is your Supabase project active?** Free Supabase projects pause after 1 week of inactivity. Go to https://supabase.com, open your project, and click **Restore** if it shows as paused.
4. **Is the password correct?** If your password contains special characters, make sure they are URL-encoded (e.g. `#` becomes `%23`).

---

## File overview

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — chat, plan review, confirm/cancel, table browser |
| `agent.py` | Gemini agentic loop — looks up DB, generates SQL plan |
| `db.py` | DB adapter — auto-switches between SQLite and PostgreSQL |
| `dummy_db.py` | Creates the local SQLite DB with sample data |
| `seed_supabase.py` | One-time seeder for Supabase PostgreSQL |
| `.env.example` | Template for your `.env` file |
| `.env` | Your local secrets — never committed to git |

---

## Sample data (pre-loaded in both databases)

| Account | Tier | Users |
|---|---|---|
| Acme Corp | Pro | alice@acme.com, bob@acme.com, carol@acme.com |
| Beta Ltd | Starter | dave@beta.com, eve@beta.com |
| Gamma Inc | Enterprise | frank@gamma.com, grace@gamma.com |
| Delta Solutions | Pro | jack@delta.com |
| Echo Partners | Starter | kate@echo.com, leo@echo.com |

Features: OCR, Translation, Analytics
