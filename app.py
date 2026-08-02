"""
app.py — Subscription Admin Agent (Streamlit)

Flow:
  1. Admin types a natural language instruction
  2. Agent looks up DB, produces a plan (summary + SQL)
  3. Admin reviews, optionally edits, then confirms
  4. On confirmation: SQL executes + audit logs written
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import db, agent
from dummy_db import build as build_dummy_db
import os

st.set_page_config(page_title="Subscription Admin Agent", page_icon="🤖", layout="wide")

# ── Seed dummy DB if it doesn't exist ─────────────────────────────────────────
if not db._use_postgres() and not os.path.exists(db.DUMMY_DB_PATH):
    build_dummy_db()

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.plan-box  { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:20px; margin:12px 0; }
.plan-title{ font-size:16px; font-weight:700; color:#0f172a; margin-bottom:8px; }
.sql-block { background:#0f172a; color:#e2e8f0; border-radius:6px; padding:12px; font-family:monospace; font-size:13px; white-space:pre-wrap; margin:6px 0; }
.warn-box  { background:#fff7ed; border:1px solid #fed7aa; border-radius:6px; padding:10px 14px; color:#9a3412; font-size:13px; margin:6px 0; }
.info-box  { background:#eff6ff; border:1px solid #bfdbfe; border-radius:6px; padding:10px 14px; color:#1e40af; font-size:13px; margin:6px 0; }
.lookup-row{ font-size:11px; color:#64748b; font-family:monospace; }
.badge-ins { background:#dcfce7; color:#166534; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.badge-upd { background:#dbeafe; color:#1e40af; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.badge-del { background:#fee2e2; color:#991b1b; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.badge-mix { background:#f3e8ff; color:#6b21a8; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.badge-sel { background:#f0fdf4; color:#166534; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.chat-user { background:#eff6ff; border-radius:10px; padding:12px 16px; margin:8px 0; }
.chat-agent{ background:#f0fdf4; border-radius:10px; padding:12px 16px; margin:8px 0; }

/* Force readable text in all input widgets */
.stTextArea textarea,
.stTextArea > div > div > textarea {
    color: #1e293b !important;
    background-color: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
}
.stTextArea textarea:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
}
.stMultiSelect span, .stSelectbox > div > div { color: #1e293b !important; }
</style>
""", unsafe_allow_html=True)

VALID_ACTIONS = ["INSERT", "UPDATE", "DELETE", "MIXED", "SELECT"]

# ── Session state defaults ─────────────────────────────────────────────────────
for k, v in {
    "history":             [],
    "pending_plan":        None,
    "pending_instruction": "",
    "undo_stack":          [],
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

conn_label = db.connection_label()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🤖 Subscription Admin Agent")
    st.markdown("---")
    icon = "🟢" if db._use_postgres() else "🟡"
    st.markdown(f"**Database:** {icon} `{conn_label}`")
    if not db._use_postgres():
        st.info("Running on SQLite dummy DB. Set `SUPABASE_DB_URL` in `.env` to connect to Supabase.")

    # ── Table Browser ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🗂 Browse Tables")
    all_tables = db.get_tables()
    selected_table = st.selectbox("Select a table:", ["— choose —"] + all_tables, key="browse_table")
    if selected_table and selected_table != "— choose —":
        try:
            your_schema_name = "uat_new" if db._use_postgres() else "prod_new"
            rows = db.query(f'SELECT * FROM "{your_schema_name}"."{selected_table}" LIMIT 200')
            if rows:
                df = pd.DataFrame(rows)
                st.caption(f"{len(rows)} row(s) shown (max 200)")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Table is empty.")
        except Exception as e:
            st.error(f"Could not read table: {e}")

    # ── What you can ask ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**What you can ask:**")
    st.markdown("""
- Deactivate a user or account
- Add a new user to an account
- Add multiple users at once
- Change an account's subscription tier
- Add or disable a feature
- Update credits for a tier
- Update tier-feature mapping
- Show me all accounts on the Pro tier
    """)

    st.markdown("---")
    if st.button("🔄 Reset conversation"):
        st.session_state.history = []
        st.session_state.pending_plan = None
        st.session_state.pending_instruction = ""
        st.rerun()

    if st.session_state.undo_stack:
        st.markdown("---")
        last = st.session_state.undo_stack[-1]
        st.markdown(f"**Last action:** {last['description']}")
        if st.button("↩️ Undo last action"):
            try:
                db.execute_transaction(last["inverse_sql"])
                st.session_state.undo_stack.pop()
                st.success("Undone successfully.")
                st.rerun()
            except Exception as e:
                st.error(f"Undo failed: {e}")

# ── Main area ─────────────────────────────────────────────────────────────────
st.markdown("## Subscription Admin Agent")
st.caption(f"Connected to: **{conn_label}**")

for msg in st.session_state.history:
    if msg["role"] == "user":
        st.markdown(f'<div class="chat-user">👤 **You:** {msg["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="chat-agent">🤖 **Agent:** {msg["content"]}</div>', unsafe_allow_html=True)

st.markdown("---")

# ── PENDING PLAN ───────────────────────────────────────────────────────────────
if st.session_state.pending_plan:
    plan = st.session_state.pending_plan

    # Clamp action_type so unknown values never crash the selectbox
    raw_action = plan.get("action_type", "MIXED")
    action_type = raw_action if raw_action in VALID_ACTIONS else "MIXED"
    is_readonly = (not plan.get("sql_statements")) or action_type == "SELECT"

    badge_map = {"INSERT":"badge-ins","UPDATE":"badge-upd","DELETE":"badge-del","MIXED":"badge-mix"}
    badge_cls = badge_map.get(action_type, "badge-sel") if not is_readonly else "badge-sel"
    badge_label = "SELECT" if is_readonly else action_type

    st.markdown(f"""
    <div class="plan-box">
      <div class="plan-title">📋 {"Query Result" if is_readonly else "Review Plan"}
        <span class="{badge_cls}">{badge_label}</span>
      </div>
      <p style="color:#334155;margin:8px 0">{plan.get("understood","")}</p>
    </div>
    """, unsafe_allow_html=True)

    for w in plan.get("warnings", []):
        st.markdown(f'<div class="warn-box">⚠️ {w}</div>', unsafe_allow_html=True)

    # ── READ-ONLY result: show lookup data as tables ───────────────────────
    if is_readonly:
        lookup_log = plan.get("lookup_log", [])
        shown = False
        for lk in lookup_log:
            rows = lk.get("rows_data") or []
            # Re-run the last lookup query to get actual data (lookup_log only stores count)
        # Re-run the understood instruction as a plain SELECT via agent lookups already done
        # Best effort: re-execute the SELECT queries from the lookup log
        st.markdown("**Results from the database:**")
        for lk in lookup_log:
            sql = lk.get("sql", "")
            if sql.strip().upper().startswith("SELECT"):
                try:
                    rows = db.query(sql)
                    if rows:
                        st.caption(f"`{sql}`")
                        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                        shown = True
                except Exception as e:
                    st.warning(f"Could not re-fetch: {e}")
        if not shown:
            st.markdown('<div class="info-box">ℹ️ The agent answered this query during planning. Check the lookups below for the data.</div>', unsafe_allow_html=True)

        if lookup_log:
            with st.expander(f"🔍 Agent lookups ({len(lookup_log)} queries)"):
                for lk in lookup_log:
                    st.markdown(f'<div class="lookup-row">{lk.get("sql","")} → {lk.get("rows","?")} rows</div>', unsafe_allow_html=True)

        if st.button("✅ Done", type="primary"):
            st.session_state.history.append({"role": "agent", "content": f"Showed results for: {plan.get('understood','')}"})
            st.session_state.pending_plan = None
            st.rerun()

    # ── WRITE PLAN: show SQL review + confirm ─────────────────────────────
    else:
        selected_tables = st.multiselect(
            "Tables that will be affected (you can change this):",
            options=all_tables,
            default=[t for t in plan.get("tables_affected", []) if t in all_tables],
        )

        action_override = st.selectbox(
            "Action type:",
            VALID_ACTIONS,
            index=VALID_ACTIONS.index(action_type),
        )

        st.markdown("**SQL that will be executed:**")
        for stmt in plan.get("sql_statements", []):
            st.markdown(f'<div class="sql-block">{stmt["sql"]}</div>', unsafe_allow_html=True)
            st.caption(f"↳ {stmt['description']}")

        if plan.get("lookup_log"):
            with st.expander(f"🔍 Agent lookups ({len(plan['lookup_log'])} queries run during planning)"):
                for lk in plan["lookup_log"]:
                    st.markdown(f'<div class="lookup-row">SELECT: {lk.get("sql","")} → {lk.get("rows","?")} rows</div>', unsafe_allow_html=True)

        with st.expander("✏️ Edit SQL before confirming"):
            edited_sqls = []
            for i, stmt in enumerate(plan.get("sql_statements", [])):
                edited = st.text_area(f"Statement {i+1}", value=stmt["sql"], key=f"sql_edit_{i}", height=80)
                edited_sqls.append({"sql": edited, "description": stmt["description"]})

        col1, col2, _ = st.columns([1, 1, 4])
        with col1:
            confirm = st.button("✅ Confirm & Execute", type="primary")
        with col2:
            cancel = st.button("❌ Cancel")

        if cancel:
            st.session_state.history.append({"role": "agent", "content": "Action cancelled. Nothing was changed."})
            st.session_state.pending_plan = None
            st.rerun()

        if confirm:
            sqls_to_run = edited_sqls if edited_sqls else plan.get("sql_statements", [])
            statements  = [(s["sql"], ()) for s in sqls_to_run]
            try:
                with st.spinner("Executing..."):
                    db.execute_transaction(statements)
                st.success(f"✅ Done! {len(statements)} statement(s) executed.")
                st.session_state.history.append({
                    "role": "agent",
                    "content": f"✅ Executed: {plan.get('understood','')} ({len(statements)} SQL statements, tables: {', '.join(selected_tables)})"
                })
                st.session_state.undo_stack.append({
                    "description": plan.get("understood",""),
                    "inverse_sql": []
                })
                st.session_state.pending_plan = None
                st.rerun()
            except Exception as e:
                st.error(f"❌ Execution failed: {e}")

# ── INPUT BOX ─────────────────────────────────────────────────────────────────
if not st.session_state.pending_plan:
    st.markdown("### What would you like to do?")

    st.markdown("**Quick actions:**")
    pills = [
        "Deactivate user alice@acme.com",
        "Add user newperson@beta.com to Beta Ltd",
        "Upgrade Acme Corp to Enterprise tier",
        "Disable the Analytics feature",
        "Show me all accounts on the Pro tier",
        "Add a new feature called 'AI Summary'",
    ]
    cols = st.columns(3)
    for i, pill in enumerate(pills):
        if cols[i % 3].button(pill, key=f"pill_{i}"):
            st.session_state["instruction_input"] = pill
            st.rerun()

    instruction = st.text_area(
        "Or type your instruction:",
        height=80,
        placeholder="e.g. Add three new users to Acme Corp: alice2@acme.com, bob2@acme.com, carol2@acme.com",
        key="instruction_input",
    )

    if st.button("🚀 Generate Plan", type="primary", disabled=not instruction.strip()):
        st.session_state.history.append({"role": "user", "content": instruction.strip()})
        with st.spinner("Agent is planning... (looking up DB, generating SQL)"):
            try:
                plan = agent.generate_plan(instruction.strip())
                st.session_state.pending_plan = plan
                st.session_state.history.append({
                    "role": "agent",
                    "content": f"Plan ready: {plan.get('understood','')} — please review below."
                })
            except Exception as e:
                st.session_state.history.append({
                    "role": "agent",
                    "content": f"❌ Could not generate plan: {e}"
                })
        st.rerun()
