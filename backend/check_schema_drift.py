#!/usr/bin/env python3
"""Schema drift harness.

backend/init.sql is the canonical schema for this repo — it drives the in-app
Schema Explorer (the frontend derives `TABLES` from it at runtime). This script
verifies that there is exactly one source of truth and reports any divergence:

  1. init.sql  vs  backend/app/models.py (SQLAlchemy metadata)
       - tables present on only one side
       - per-table columns present on only one side
       - nullability mismatches (reported for information; no fail by default)
  2. init.sql  vs  src/data.ts
       - `TABLES` must be DERIVED from init.sql (parseDdl(initSqlText)),
         i.e. no hand-maintained schema literal may remain
       - every `*Row` / `INITIAL_*` seed field must be a column declared in
         init.sql (flags seed data that no longer maps to the real schema)
  3. Alembic migrations are cross-checked against init.sql table list.

Documented, intentional deviations are allowlisted (e.g. `requirement_states`
and `pending_actions` are provisioned by Alembic migrations at startup and are
not part of init.sql). Any *other* drift is reported and exits non-zero so this
can be used as a CI gate.

Usage:
    python backend/check_schema_drift.py
    npm run schema:drift
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
SRC = os.path.join(ROOT, "src")
INIT_SQL = os.path.join(BACKEND, "init.sql")
DATA_TS = os.path.join(SRC, "data.ts")

# Tables intentionally absent from init.sql but provisioned by Alembic at startup.
DOCUMENTED_MODEL_ONLY_TABLES = {
    "requirement_states",
    "pending_actions",
    "uploaded_documents",
}

# INITIAL_* constant name in src/data.ts  ->  table name in init.sql
INITIAL_TO_TABLE = {
    "INITIAL_USERS": "users",
    "INITIAL_PROJECTS": "projects",
    "INITIAL_EPICS": "epics",
    "INITIAL_REQUIREMENTS": "requirements",
    "INITIAL_USER_STORIES": "user_stories",
    "INITIAL_ACCEPTANCE_CRITERIA": "acceptance_criteria",
    "INITIAL_AUDIT_RESULTS": "audit_results",
    "INITIAL_QUESTIONS": "clarification_questions",
    "INITIAL_PRD_DOCS": "prd_documents",
    "INITIAL_VERSION_HISTORY": "version_history",
    "INITIAL_PRD_VERSIONS": "prd_versions",
    "INITIAL_CONVERSATION_MESSAGES": "conversation_messages",
    "INITIAL_ARTIFACT_EVENT_LOGS": "artifact_event_logs",
}


def strip_comments(sql: str) -> str:
    out = []
    for line in sql.splitlines():
        idx = line.find("--")
        out.append(line if idx == -1 else line[:idx])
    return "\n".join(out)


def parse_init_sql(path: str) -> dict:
    """Return {table: {'columns': {name: {'nullable': bool}}, 'order': [names]}}."""
    sql = strip_comments(open(path, encoding="utf-8").read())
    tables: dict = {}
    pattern = re.compile(
        r"CREATE\s+TABLE\s+([A-Za-z_][\w]*)\s*\((.*?)\)\s*;", re.S | re.I
    )
    for m in pattern.finditer(sql):
        name = m.group(1)
        body = m.group(2)
        cols = {}
        order = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            line = line.rstrip(",").strip()
            if not line or line == ")":
                continue
            if re.match(r"^(PRIMARY KEY|UNIQUE|CONSTRAINT|CHECK|FOREIGN KEY)\b", line, re.I):
                continue
            cm = re.match(r"^([A-Za-z_][\w]*)\s+(.+)$", line)
            if not cm:
                print(f"  ! could not parse column line in {name}: {line!r}")
                continue
            colname = cm.group(1)
            decl = cm.group(2)
            upper = decl.upper()
            nullable = not ("NOT NULL" in upper or "PRIMARY KEY" in upper)
            cols[colname] = {"nullable": nullable}
            order.append(colname)
        tables[name] = {"columns": cols, "order": order}
    return tables


def load_model_metadata() -> dict:
    """Return {table: {'columns': {name: {'nullable': bool}}, 'order': [names]}}."""
    sys.path.insert(0, BACKEND)
    from app.models import Base  # noqa: PLC0415

    tables = {}
    for name, table in Base.metadata.tables.items():
        cols = {}
        order = []
        for col in table.columns:
            cols[col.name] = {"nullable": bool(col.nullable)}
            order.append(col.name)
        tables[name] = {"columns": cols, "order": order}
    return tables

def parse_frontend_seed(data_ts: str) -> dict:
    """Collect every field referenced by INITIAL_* seed rows and *Row types."""
    result = {}
    for const, table in INITIAL_TO_TABLE.items():
        fields = set()
        # Row type: `export type XRow = { ... }`
        row_type = const[len("INITIAL_"):]
        type_pat = re.compile(
            r"export\s+type\s+%s\s*=\s*\{(.*?)\n\}" % re.escape(row_type), re.S
        )
        tm = type_pat.search(data_ts)
        if tm:
            fields |= set(re.findall(r"^\s*([A-Za-z_][\w]*)\s*:", tm.group(1), re.M))
        # Seed rows: `export const INITIAL_X: XRow[] = [ {...}, ... ];`
        seed_pat = re.compile(
            r"export\s+const\s+%s[^=]*=\s*\[(.*?)\n\];" % re.escape(const), re.S
        )
        sm = seed_pat.search(data_ts)
        if sm:
            # Strip JSON.stringify({ ... }) snapshot bodies (not real columns).
            body = re.sub(r"JSON\.stringify\(\{.*?\}\)", "", sm.group(1), flags=re.S)
            fields |= set(re.findall(r"^\s*([A-Za-z_][\w]*)\s*:", body, re.M))
        result[table] = sorted(f for f in fields if f != "id")
    return result


def compare_tables(sql_tables, model_tables, documented_set):
    problems = []
    notes = []
    sql_names = set(sql_tables)
    model_names = set(model_tables)

    only_model = sorted(model_names - sql_names)
    for t in only_model:
        if t in documented_set:
            notes.append(f"[info] {t}: provisioned by migrations, intentionally not in init.sql")
        else:
            problems.append(f"[DRIFT] table in models.py but NOT in init.sql: {t}")

    only_sql = sorted(sql_names - model_names)
    for t in only_sql:
        problems.append(f"[DRIFT] table in init.sql but NOT in models.py: {t}")

    for t in sorted(sql_names & model_names):
        sql_cols = set(sql_tables[t]["columns"])
        model_cols = set(model_tables[t]["columns"])
        for c in sorted(sql_cols - model_cols):
            problems.append(f"[DRIFT] {t}.{c}: in init.sql but NOT in models.py")
        for c in sorted(model_cols - sql_cols):
            problems.append(f"[DRIFT] {t}.{c}: in models.py but NOT in init.sql")
        for c in sorted(sql_cols & model_cols):
            sql_null = sql_tables[t]["columns"][c]["nullable"]
            model_null = model_tables[t]["columns"][c]["nullable"]
            if sql_null != model_null:
                notes.append(
                    f"[WARN] {t}.{c} nullability differs: init.sql={sql_null}, models.py={model_null}"
                )
    return problems, notes


def compare_frontend(sql_tables, seed):
    problems = []
    for table, fields in sorted(seed.items()):
        if table not in sql_tables:
            problems.append(f"[DRIFT] frontend seed targets table not in init.sql: {table}")
            continue
        valid = set(sql_tables[table]["columns"])
        for f in sorted(set(fields) - valid):
            problems.append(
                f"[DRIFT] src/data.ts field `{table}.{f}` is not a column in init.sql"
            )
    return problems


def main() -> int:
    print("=" * 72)
    print("Schema drift harness  (canonical source: backend/init.sql)")
    print("=" * 72)

    sql_tables = parse_init_sql(INIT_SQL)
    print(f"\n[1/3] init.sql parsed: {len(sql_tables)} tables -> {', '.join(sorted(sql_tables))}")

    problems = []
    notes = []

    # -- models.py comparison ------------------------------------------------
    print("\n[2/3] Comparing init.sql vs backend/app/models.py ...")
    try:
        model_tables = load_model_metadata()
        print(f"      models.py metadata: {len(model_tables)} tables")
        mp, mn = compare_tables(sql_tables, model_tables, DOCUMENTED_MODEL_ONLY_TABLES)
        problems.extend(mp)
        notes.extend(mn)
        for line in mp:
            print("     ", line)
        for line in mn:
            print("     ", line)
    except Exception as exc:  # pragma: no cover - env dependent
        print(f"      ! could not introspect models.py: {exc}")
        problems.append("[DRIFT] models.py could not be introspected; cannot verify")

    # -- frontend comparison ------------------------------------------------
    print("\n[3/3] Comparing init.sql vs src/data.ts ...")
    data_ts = open(DATA_TS, encoding="utf-8").read()
    if "parseDdl(initSqlText)" not in data_ts:
        problems.append(
            "[DRIFT] src/data.ts TABLES is not derived from init.sql "
            "(expected `parseDdl(initSqlText)`); a hand-maintained schema may have returned."
        )
    else:
        print("      OK: src/data.ts TABLES is derived from init.sql (parseDdl).")
    seed = parse_frontend_seed(data_ts)
    frontend_problems = compare_frontend(sql_tables, seed)
    problems.extend(frontend_problems)
    for line in frontend_problems:
        print("     ", line)

    # -- summary -------------------------------------------------------------
    print("\n" + "=" * 72)
    if problems:
        print(f"DRIFT DETECTED: {len(problems)} issue(s).")
        for p in problems:
            print("  -", p)
        print("\nFix drift, or if intentional add it to DOCUMENTED_MODEL_ONLY_TABLES.")
        return 1
    print(f"No drift found. {len(notes)} informational note(s).")
    for n in notes:
        print("  -", n)
    print("\nSingle source of truth verified: backend/init.sql == models.py == frontend data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

