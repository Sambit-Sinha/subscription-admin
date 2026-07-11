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

---

## Prerequisites

- Python 3.9 or higher
- A free Google Gemini API key — get one at https://aistudio.google.com/app/apikey (1 500 free requests/day)
- (Optional) A Supabase PostgreSQL URL if you want a real cloud DB instead of the local dummy

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

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and set:

```
GEMINI_API_KEY=your_key_here
```

Leave `SUPABASE_DB_URL` blank (or remove it) to use the local SQLite dummy database.
The dummy DB is created automatically on first run — no setup needed.

### 5. Run the app

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501** in your browser.

---

## Using Supabase instead of the dummy DB (optional)

1. Create a free project at https://supabase.com
2. Copy your connection string from **Project Settings → Database → Connection string (URI)**
3. Add it to `.env`:
   ```
   SUPABASE_DB_URL=postgresql://postgres:YOUR_PASSWORD@YOUR_PROJECT.supabase.co:5432/postgres
   ```
4. Run the seeder once to create tables and load sample data:
   ```bash
   python seed_supabase.py
   ```
5. Start the app as normal — it will automatically use PostgreSQL.

---

## File overview

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — chat, plan review, confirm/cancel |
| `agent.py` | Gemini agentic loop — looks up DB, generates SQL plan |
| `db.py` | DB adapter — switches between SQLite and PostgreSQL |
| `dummy_db.py` | Creates the local SQLite DB with sample data |
| `seed_supabase.py` | One-time seeder for Supabase PostgreSQL |
| `.env.example` | Template for your `.env` file |

---

## Sample data (dummy DB)

| Account | Tier | Users |
|---|---|---|
| Acme Corp | Pro | alice@acme.com, bob@acme.com, carol@acme.com |
| Beta Ltd | Starter | dave@beta.com, eve@beta.com |
| Gamma Inc | Enterprise | frank@gamma.com, grace@gamma.com |
| Delta Solutions | Pro | jack@delta.com |
| Echo Partners | Starter | kate@echo.com, leo@echo.com |

Features: OCR, Translation, Analytics
