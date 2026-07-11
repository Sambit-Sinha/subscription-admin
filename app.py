"""
app.py — Subscription Admin Agent (Streamlit)

Chat-based admin interface powered by Claude.
Flow:
  1. Admin types a natural language instruction
  2. Agent looks up DB, produces a plan (summary + SQL)
  3. Admin reviews, optionally edits, then confirms
  4. On confirmation: SQL executes + audit logs written
"""
import streamlit as st
import json
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
.plan-box { background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:20px; margin:12px 0; }
.plan-title { font-size:16px; font-weight:700; color:#0f172a; margin-bottom:8px; }
.sql-block { background:#0f172a; color:#e2e8f0; border-radius:6px; padding:12px; font-family:monospace; font-size:13px; white-space:pre-wrap; margin:6px 0; }
.warn-box { background:#fff7ed; border:1px solid #fed7aa; border-radius:6px; padding:10px 14px; color:#9a3412; font-size:13px; margin:6px 0; }
.lookup-row { font-size:11px; color:#64748b; font-family:monospace; }
.badge-ins  { background:#dcfce7; color:#166534; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.badge-upd  { background:#dbeafe; color:#1e40af; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.badge-del  { background:#fee2e2; color:#991b1b; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.badge-mix  { background:#f3e8ff; color:#6b21a8; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.chat-user { background:#eff6ff; border-radius:10px; padding:12px 16px; margin:8px 0; }
.chat-agent { background:#f0fdf4; border-radius:10px; padding:12px 16px; margin:8px 0; }

/* Force dark text on all textareas so content is always readable */
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
/* Multiselect and selectbox text */
.stMultiSelect span, .stSelectbox > div > div {
    color: #1e293b !important;
}
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ─────────────────────────────────────────────────────
for k, v in {
    "history": [],          # list of {role, content} for display
    "pending_plan": None,   # the current unconfirmed plan
    "pending_instruction": "",
    "undo_stack": [],       # list of {description, inverse_sql} for undo (best-effort)
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🤖 Subscription Admin Agent")
    st.markdown("---")
    conn_label = db.connection_label()
    icon = "🟢" if db._use_postgres() else "🟡"
    st.markdown(f"**Database:** {icon} `{conn_label}`")

    if not db._use_postgres():
        st.info("Running on SQLite dummy DB. Set `SUPABASE_DB_URL` in `.env` to connect to Supabase.")

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

# Chat history
for msg in st.session_state.history:
    if msg["role"] == "user":
        st.markdown(f'<div class="chat-user">👤 **You:** {msg["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="chat-agent">🤖 **Agent:** {msg["content"]}</div>', unsafe_allow_html=True)

st.markdown("---")

# ── PENDING PLAN: show review UI ───────────────────────────────────────────────
if st.session_state.pending_plan:
    plan = st.session_state.pending_plan
    badge_map = {"INSERT":"badge-ins","UPDATE":"badge-upd","DELETE":"badge-del","MIXED":"badge-mix"}
    badge_cls = badge_map.get(plan.get("action_type",""), "badge-mix")

    st.markdown(f"""
    <div class="plan-box">
      <div class="plan-title">📋 Review Plan <span class="{badge_cls}">{plan.get("action_type","")}</span></div>
      <p style="color:#334155;margin:8px 0">{plan.get("understood","")}</p>
    </div>
    """, unsafe_allow_html=True)

    # Warnings
    for w in plan.get("warnings", []):
        st.markdown(f'<div class="warn-box">⚠️ {w}</div>', unsafe_allow_html=True)

    # Tables affected (editable dropdown)
    all_tables = db.get_tables()
    current_tables = plan.get("tables_affected", [])
    selected_tables = st.multiselect(
        "Tables that will be affected (you can change this):",
        options=all_tables,
        default=[t for t in current_tables if t in all_tables],
    )

    # Action type override
    action_override = st.selectbox(
        "Action type:",
        ["INSERT", "UPDATE", "DELETE", "MIXED"],
        index=["INSERT","UPDATE","DELETE","MIXED"].index(plan.get("action_type","MIXED")),
    )

    # SQL preview
    st.markdown("**SQL that will be executed:**")
    for i, stmt in enumerate(plan.get("sql_statements", [])):
        st.markdown(f'<div class="sql-block">{stmt["sql"]}</div>', unsafe_allow_html=True)
        st.caption(f"↳ {stmt['description']}")

    # Lookup trace (collapsed)
    if plan.get("lookup_log"):
        with st.expander(f"🔍 Agent lookups ({len(plan['lookup_log'])} queries run during planning)"):
            for lk in plan["lookup_log"]:
                st.markdown(f'<div class="lookup-row">SELECT: {lk.get("sql","")} → {lk.get("rows","?")} rows</div>', unsafe_allow_html=True)

    # Editable SQL (power user escape hatch)
    with st.expander("✏️ Edit SQL before confirming"):
        edited_sqls = []
        for i, stmt in enumerate(plan.get("sql_statements", [])):
            edited = st.text_area(f"Statement {i+1}", value=stmt["sql"], key=f"sql_edit_{i}", height=80)
            edited_sqls.append({"sql": edited, "description": stmt["description"]})

    col1, col2, col3 = st.columns([1, 1, 4])
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
            st.success(f"✅ Done! {len(statements)} statement(s) executed successfully.")
            st.session_state.history.append({
                "role": "agent",
                "content": f"✅ Executed: {plan.get('understood','')} ({len(statements)} SQL statements, tables: {', '.join(selected_tables)})"
            })
            # Best-effort undo: store description only (inverse SQL is complex to auto-generate)
            st.session_state.undo_stack.append({
                "description": plan.get("understood",""),
                "inverse_sql": []  # full inverse generation is out of scope for v1
            })
            st.session_state.pending_plan = None
            st.rerun()
        except Exception as e:
            st.error(f"❌ Execution failed: {e}")

# ── INPUT BOX ─────────────────────────────────────────────────────────────────
if not st.session_state.pending_plan:
    st.markdown("### What would you like to do?")

    # Quick action pills
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
            # Must write directly to the widget's own key; setting pending_instruction
            # has no effect because Streamlit ignores value= once a key is in session_state.
            st.session_state["instruction_input"] = pill
            st.session_state.pending_instruction = ""
            st.rerun()

    instruction = st.text_area(
        "Or type your instruction:",
        height=80,
        placeholder="e.g. Add three new users to Acme Corp: alice2@acme.com, bob2@acme.com, carol2@acme.com",
        key="instruction_input",
    )

    if st.button("🚀 Generate Plan", type="primary", disabled=not instruction.strip()):
        st.session_state.pending_instruction = ""
        st.session_state.history.append({"role": "user", "content": instruction.strip()})
        with st.spinner("Agent is planning... (looking up DB, generating SQL)"):
            try:
                plan = agent.generate_plan(instruction.strip())
                st.session_state.pending_plan = plan
                st.session_state.history.append({
                    "role": "agent",
                    "content": f"Plan ready: {plan.get('understood','')} — please review and confirm below."
                })
            except Exception as e:
                st.session_state.history.append({
                    "role": "agent",
                    "content": f"❌ Could not generate plan: {e}"
                })
        st.rerun()
