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
from google.genai import types
import db

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

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
"""

# ── Tool declarations ──────────────────────────────────────────────────────────
_lookup_decl = types.FunctionDeclaration(
    name="lookup",
    description="Run a read-only SELECT query to resolve names, find IDs, check current values.",
    parameters=types.Schema(
        type="OBJECT",
        properties={"sql": types.Schema(type="STRING", description="A SELECT query.")},
        required=["sql"],
    ),
)

_produce_plan_decl = types.FunctionDeclaration(
    name="produce_plan",
    description="Output the final change plan after all lookups are complete.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "understood":      types.Schema(type="STRING"),
            "action_type":     types.Schema(type="STRING", enum=["INSERT","UPDATE","DELETE","MIXED"]),
            "tables_affected": types.Schema(type="ARRAY", items=types.Schema(type="STRING")),
            "warnings":        types.Schema(type="ARRAY", items=types.Schema(type="STRING")),
            "sql_statements":  types.Schema(
                type="ARRAY",
                items=types.Schema(
                    type="OBJECT",
                    properties={
                        "sql":         types.Schema(type="STRING"),
                        "description": types.Schema(type="STRING"),
                    },
                    required=["sql", "description"],
                ),
            ),
        },
        required=["understood","action_type","tables_affected","warnings","sql_statements"],
    ),
)

_tools = types.Tool(function_declarations=[_lookup_decl, _produce_plan_decl])


def generate_plan(instruction: str) -> dict:
    """
    Agentic loop:
      - Gemini calls 'lookup' as many times as needed (read-only)
      - Gemini calls 'produce_plan' with the final structured plan
      - We return that plan dict
    """
    # Build conversation history manually so we can inject function results
    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=instruction)])
    ]
    lookup_log = []

    for _ in range(12):   # max 12 rounds
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[_tools],
            ),
        )

        # Append model response to history
        contents.append(types.Content(role="model", parts=response.candidates[0].content.parts))

        # Find function calls
        fn_calls = [p for p in response.candidates[0].content.parts if p.function_call]
        if not fn_calls:
            break   # model replied with text — no more tool calls

        # Process each function call
        fn_response_parts = []
        plan_result = None

        for p in fn_calls:
            fc = p.function_call

            if fc.name == "lookup":
                sql = fc.args.get("sql", "")
                try:
                    rows = db.query(sql)
                    result = {"rows": rows[:50]}
                    lookup_log.append({"sql": sql, "rows": len(rows)})
                except Exception as e:
                    result = {"error": str(e)}
                    lookup_log.append({"sql": sql, "error": str(e)})
                fn_response_parts.append(types.Part(
                    function_response=types.FunctionResponse(name="lookup", response=result)
                ))

            elif fc.name == "produce_plan":
                plan_result = {
                    "understood":      str(fc.args.get("understood", "")),
                    "action_type":     str(fc.args.get("action_type", "MIXED")),
                    "tables_affected": list(fc.args.get("tables_affected", [])),
                    "warnings":        list(fc.args.get("warnings", [])),
                    "sql_statements":  [dict(s) for s in fc.args.get("sql_statements", [])],
                    "lookup_log":      lookup_log,
                }
                fn_response_parts.append(types.Part(
                    function_response=types.FunctionResponse(
                        name="produce_plan", response={"status": "received"}
                    )
                ))

        # Return plan if we got one
        if plan_result:
            return plan_result

        # Otherwise send function results back and loop
        contents.append(types.Content(role="user", parts=fn_response_parts))

    return {
        "understood":      "Could not generate a plan.",
        "action_type":     "UNKNOWN",
        "tables_affected": [],
        "warnings":        ["Agent loop ended without a plan. Try rephrasing your instruction."],
        "sql_statements":  [],
        "lookup_log":      lookup_log,
    }
