"""
agent.py — Claude-powered plan generator.

Given a natural language admin instruction, this module:
  1. Lets Claude look up the DB to resolve names → IDs (read-only planning phase)
  2. Returns a structured Plan: summary, SQL statements, tables affected, warnings
  3. Never writes to the DB — that only happens after the human confirms
"""
import json, os
import anthropic
import db

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

SCHEMA_DESCRIPTION = """
DATABASE SCHEMA (exact column names — use only these):

subscription_tier      : subscription_tier_id, tier_name, total_credits
subscription_tier_log  : subscription_tier_log_id, subscription_tier_id, action, details, created_date
features               : feature_id, feature_name, description, active_flag
features_log           : feature_log_id, feature_id, action, details, created_date
tier_feature_mapping   : mapping_pk, subscription_tier_id, feature_id, capability_included, credit_per_click_tier, file_limit
tier_feature_mapping_log: mapping_log_id, mapping_pk, action, old_value, new_value, created_date
account                : account_id, account_name, subscription_tier_id, active_account, start_date, end_date, created_by, created_date, modified_by, modified_date
account_plan           : account_plan_id, account_id, subscription_tier_id, start_date, end_date, created_by, created_date, modified_by, modified_date
account_log            : account_log_id, account_id, subscription_tier_id, old_tier_id, description, start_date, end_date, created_by, created_date, modified_by, modified_date
user                   : user_pk, account_id, user_id, active_user, user_email, created_by, created_date, modified_by, modified_date  (table name must be quoted as "user")
user_log               : user_log_id, user_id, account_id, action, details, created_by, created_date
usage_log              : usage_log_id, user_id, account_id, feature_id, subscription_tier_id, account_plan_id, success_indicator, no_of_files, usage_timestamp

RULES:
- active_account: 1=active, 0=inactive
- active_user: 1=active, 0=inactive
- active_flag (features): 1=enabled, 0=disabled
- Every data change MUST be accompanied by an INSERT into the corresponding *_log table.
- Log tables for each main table: account→account_log, user→user_log, features→features_log, subscription_tier→subscription_tier_log, tier_feature_mapping→tier_feature_mapping_log
- usage_log has no log table — it is itself the log.
- Use CURRENT_TIMESTAMP for created_date / modified_date / created_date defaults.
- Placeholder for parameters: use ? (SQLite) or %s (PostgreSQL) — the app will substitute actual values.
  Instead, write COMPLETE SQL with literal values filled in wherever possible from your lookups.
- For user table always quote it as: "user"
"""

SYSTEM_PROMPT = f"""You are a database admin agent for a subscription management system.
Your job: understand a natural language admin instruction, look up the database to resolve any ambiguous names or IDs,
then produce a precise, safe change plan.

{SCHEMA_DESCRIPTION}

WORKFLOW:
1. Use the 'lookup' tool to run SELECT queries to find exact IDs, names, current values for anything mentioned.
2. After all lookups, call 'produce_plan' with a complete, ready-to-execute plan.

PRODUCE_PLAN OUTPUT FORMAT:
{{
  "understood": "plain English summary of what you will do",
  "action_type": "INSERT | UPDATE | DELETE | MIXED",
  "tables_affected": ["table1", "table1_log", ...],
  "warnings": ["any risks, e.g. this will affect N users"],
  "sql_statements": [
    {{"sql": "...", "description": "what this statement does"}},
    ...
  ]
}}

IMPORTANT:
- Always include the log INSERT after every data change.
- Fill in actual values from your lookups — no placeholders like <account_id>.
- If instruction is ambiguous and lookup returns multiple matches, list them in warnings and ask for clarification instead of guessing.
- Never include SELECT statements in sql_statements — only INSERT/UPDATE/DELETE.
"""

lookup_tool = {
    "name": "lookup",
    "description": "Run a read-only SELECT query on the database to resolve names, find IDs, or check current values before planning changes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "A SELECT query. Must be read-only."}
        },
        "required": ["sql"]
    }
}

produce_plan_tool = {
    "name": "produce_plan",
    "description": "Output the final change plan as structured JSON after all lookups are complete.",
    "input_schema": {
        "type": "object",
        "properties": {
            "understood":      {"type": "string"},
            "action_type":     {"type": "string", "enum": ["INSERT", "UPDATE", "DELETE", "MIXED"]},
            "tables_affected": {"type": "array", "items": {"type": "string"}},
            "warnings":        {"type": "array", "items": {"type": "string"}},
            "sql_statements":  {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sql":         {"type": "string"},
                        "description": {"type": "string"}
                    },
                    "required": ["sql", "description"]
                }
            }
        },
        "required": ["understood", "action_type", "tables_affected", "warnings", "sql_statements"]
    }
}


def generate_plan(instruction: str) -> dict:
    """
    Run the agentic loop:
      - Claude calls 'lookup' as many times as needed (read-only)
      - Claude calls 'produce_plan' once with the final structured plan
      - We return that plan dict to the caller
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": instruction}]
    lookup_log = []

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[lookup_tool, produce_plan_tool],
            messages=messages,
        )

        # Collect tool uses in this response
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            # Claude responded with text but no tool call — shouldn't happen but handle gracefully
            return {
                "understood": response.content[0].text if response.content else "No plan generated.",
                "action_type": "UNKNOWN",
                "tables_affected": [],
                "warnings": ["Agent did not produce a structured plan. Try rephrasing."],
                "sql_statements": [],
                "lookup_log": lookup_log,
            }

        # Build tool results to send back
        tool_results = []
        plan_result  = None

        for tu in tool_uses:
            if tu.name == "lookup":
                sql = tu.input.get("sql", "")
                try:
                    rows = db.query(sql)
                    result_text = json.dumps(rows[:50])  # cap at 50 rows
                    lookup_log.append({"sql": sql, "rows": len(rows)})
                except Exception as e:
                    result_text = json.dumps({"error": str(e)})
                    lookup_log.append({"sql": sql, "error": str(e)})
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result_text})

            elif tu.name == "produce_plan":
                plan_result = tu.input
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "Plan received."})

        # Append assistant response + tool results to messages
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user",      "content": tool_results})

        # If we got the final plan, return it
        if plan_result is not None:
            plan_result["lookup_log"] = lookup_log
            return plan_result

        # Otherwise loop — Claude will use more tools
        if response.stop_reason == "end_turn":
            break

    return {
        "understood": "Could not generate a plan.",
        "action_type": "UNKNOWN",
        "tables_affected": [],
        "warnings": ["Agent loop ended without producing a plan."],
        "sql_statements": [],
        "lookup_log": lookup_log,
    }
