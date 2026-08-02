"""
agent.py — Gemini-powered plan generator (free tier: 1500 requests/day).
Uses google-genai (the current, non-deprecated SDK).

Given a natural language admin instruction, this module:
  1. Lets Gemini look up the DB to resolve names → IDs (read-only planning phase)
  2. Returns a structured Plan: summary, SQL statements, tables affected, warnings
  3. Never writes to the DB — that only happens after the human confirms
"""
import json, os
from google import genai
from openai import OpenAI
import db
from dotenv import load_dotenv

load_dotenv('.env.example')  # load GEMINI_API_KEY from .env
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),          # or TOGETHER_API_KEY, OPENROUTER_API_KEY, etc.
    base_url="https://api.groq.com/openai/v1",  # change per provider
)
SCHEMA_DESCRIPTION = """
DATABASE SCHEMA (exact column names — use only these):
IMPORTANT: All table names must be prefixed with the schema name "uat_new" (e.g., "your_schema_name"."table_name").

subscription_tier      : subscription_tier_id, tier_name, total_credits
subscription_tier_log  : subscription_tier_log_id, subscription_tier_id, action, details, created_date
features               : feature_id, feature_name, description, active_flag
features_log           : feature_log_id, feature_id, action, details, created_date
tier_feature_mapping   : mapping_pk, subscription_tier_id, feature_id, capability_included, credit_per_click_tier, file_limit
tier_feature_mapping_log: mapping_log_id, mapping_pk, action, old_value, new_value, created_date
account                : account_id, account_name, subscription_tier_id, active_account, start_date, end_date, created_by, created_date, modified_by, modified_date
account_plan           : account_plan_id, account_id, subscription_tier_id, start_date, end_date, created_by, created_date, modified_by, modified_date
account_log            : account_log_id, account_id, subscription_tier_id, old_tier_id, description, start_date, end_date, created_by, created_date, modified_by, modified_date
user                   : user_pk, account_id, user_id, active_user, user_email, created_by, created_date, modified_by, modified_date  (MUST be quoted as "user" in SQL)
user_log               : user_log_id, user_id, account_id, action, details, created_by, created_date
usage_log              : usage_log_id, user_id, account_id, feature_id, subscription_tier_id, account_plan_id, success_indicator, no_of_files, usage_timestamp

RULES:
- active_account: 1=active, 0=inactive. active_user: 1=active, 0=inactive. active_flag: 1=enabled, 0=disabled.
- Every data change MUST be followed by an INSERT into the corresponding *_log table.
- Log table map: account→account_log, user→user_log, features→features_log,
  subscription_tier→subscription_tier_log, tier_feature_mapping→tier_feature_mapping_log.
  usage_log has no separate log.
- In SQL always write the user table as: "user" (double quotes required).
- Write complete SQL with literal values filled in from your lookups. No placeholders.
- sql_statements must contain only INSERT/UPDATE/DELETE — no SELECT.
"""

SYSTEM_PROMPT = f"""You are a database admin agent for a subscription management system.
Understand a natural language admin instruction, look up the DB to resolve names/IDs,
then produce a precise, safe change plan.

{SCHEMA_DESCRIPTION}

WORKFLOW:
1. Call 'lookup' (as many times as needed) to SELECT and find exact IDs, current values.
2. Always call 'produce_plan' once at the end — even for read-only queries.

produce_plan fields:
- understood: plain English summary of what was found or what will be done
- action_type: INSERT | UPDATE | DELETE | MIXED | SELECT
  Use SELECT when the instruction is read-only (no changes needed).
- tables_affected: list of table names queried or changed
- warnings: risks, row counts affected, anything the admin should know
- sql_statements: list of {{sql, description}} — INSERT/UPDATE/DELETE only, never SELECT.
  Leave empty [] for read-only instructions.

If ambiguous (multiple matches found), set sql_statements=[] and explain in warnings.
For read-only instructions ("show me", "list", "how many"), set action_type=SELECT and sql_statements=[].

IMPORTANT RULES FOR TOOL USE:
- You MUST use the provided tools (lookup and produce_plan).
- Never answer with plain text when a tool call is needed.
- When you are ready to give the final answer, you MUST call the produce_plan tool.
- Do not output any text outside of tool calls until the plan is produced.
- Always call produce_plan as the last step.
"""

# ── Tool declarations ──────────────────────────────────────────────────────────
tools = [
    {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "Run a read-only SELECT query to resolve names, find IDs, check current values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "A SELECT query."}
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "produce_plan",
            "description": "Output the final change plan after all lookups are complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "understood":      {"type": "string"},
                    "action_type":     {"type": "string", "enum": ["INSERT", "UPDATE", "DELETE", "MIXED", "SELECT"]},
                    "tables_affected": {"type": "array", "items": {"type": "string"}},
                    "warnings":        {"type": "array", "items": {"type": "string"}},
                    "sql_statements":  {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sql":         {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["sql", "description"],
                        },
                    },
                },
                "required": ["understood", "action_type", "tables_affected", "warnings", "sql_statements"],
            },
        },
    },
]


def generate_plan(instruction: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": instruction},
    ]
    lookup_log = []

    for _ in range(12):
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tools,
            tool_choice="auto",          # or "required" if you always want a tool call
            temperature=0.1,             # lower = more reliable tool calls
            max_tokens=1024,             # give it enough room
        )

        msg = response.choices[0].message
        messages.append(msg)  # append the whole message (includes tool_calls)

        if not msg.tool_calls:
            break

        plan_result = None
        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)

            if name == "lookup":
                sql = args.get("sql", "")
                try:
                    rows = db.query(sql)
                    result = {"rows": json.loads(json.dumps(rows[:50], default=str))}
                    lookup_log.append({"sql": sql, "rows": len(rows)})
                except Exception as e:
                    result = {"error": str(e)}
                    lookup_log.append({"sql": sql, "error": str(e)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

            elif name == "produce_plan":
                plan_result = {
                    "understood":      str(args.get("understood", "")),
                    "action_type":     str(args.get("action_type", "MIXED")),
                    "tables_affected": list(args.get("tables_affected", [])),
                    "warnings":        list(args.get("warnings", [])),
                    "sql_statements":  [dict(s) for s in args.get("sql_statements", [])],
                    "lookup_log":      lookup_log,
                }
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"status": "received"}),
                })

        if plan_result:
            return plan_result

    return {
        "understood": "Could not generate a plan.",
        "action_type": "UNKNOWN",
        "tables_affected": [],
        "warnings": ["Agent loop ended without a plan. Try rephrasing your instruction."],
        "sql_statements": [],
        "lookup_log": lookup_log,
    }
