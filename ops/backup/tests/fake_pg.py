"""
Stand-ins for pg_dump / pg_restore / psql / gpg, run as real processes by the tests (no
PostgreSQL is installed or contacted). Behaviour is steered with FAKE_* environment variables;
every call is appended to FAKE_LOG so tests can check what was (and wasn't) run.

A fake "archive" is b"PGDMP" + JSON of its table names, enough for --list and restore.
"""
import json
import os
import sys

tool, args = sys.argv[1], sys.argv[2:]


def record(**extra):
    path = os.environ.get("FAKE_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"tool": tool, "args": args, "env_has_pgpassword": "PGPASSWORD" in os.environ,
                                "pgpassfile": os.environ.get("PGPASSFILE"), **extra}) + "\n")


def password():
    p = os.environ.get("PGPASSFILE")
    if p and os.path.exists(p):
        return open(p, encoding="utf-8").read().strip().split(":", 4)[-1]
    return ""


def fail(code, msg):
    sys.stderr.write(msg + "\n")
    sys.exit(code)


tables = [t for t in os.environ.get("FAKE_PG_DUMP_TABLES", "public.users,public.questions,public.exam_submissions").split(",") if t]

if tool == "pg_dump":
    record()
    if "--version" in args:
        print("pg_dump (PostgreSQL) " + os.environ.get("FAKE_PG_DUMP_VERSION", "16.4"))
        sys.exit(0)
    if os.environ.get("FAKE_PG_DUMP_FAIL"):
        # A real pg_dump error can quote the connection; the tool must redact it.
        fail(1, f'pg_dump: error: query failed: permission denied for table users '
                f'(postgresql://{os.environ.get("PGUSER")}:{password()}@{os.environ.get("PGHOST")}/x password={password()})')
    payload = b"PGDMP\x01" + json.dumps(tables).encode() + b"\x00" * 200_000
    sys.stdout.buffer.write(payload)
    sys.exit(0)

if tool == "pg_restore":
    data = sys.stdin.buffer.read()
    if "--list" in args:
        record(bytes=len(data))
        if not data.startswith(b"PGDMP"):
            fail(1, "pg_restore: error: input file does not appear to be a valid archive")
        names = json.loads(data[6:data.index(b"]") + 1])
        print(";\n; Archive created at 2026-11-02 02:30:00 UTC\n;")
        for i, t in enumerate(names):
            s, n = t.split(".", 1)
            print(f"{200 + i}; 1259 {16390 + i} TABLE {s} {n} oraliq")
        for i, t in enumerate(names):
            s, n = t.split(".", 1)
            print(f"{3400 + i}; 0 {16390 + i} TABLE DATA {s} {n} oraliq")
        sys.exit(0)
    record(bytes=len(data), restore=True)
    if os.environ.get("FAKE_RESTORE_FAIL"):
        fail(1, "pg_restore: error: could not execute query: ERROR:  relation already exists")
    names = json.loads(data[6:data.index(b"]") + 1])
    state = os.environ.get("FAKE_STATE")
    if state:
        drop = set(os.environ.get("FAKE_RESTORE_DROP", "").split(","))
        json.dump([t for t in names if t not in drop], open(state, "w"))
    sys.exit(0)

if tool == "psql":
    sql = args[args.index("-c") + 1] if "-c" in args else ""
    record(sql=sql)
    if os.environ.get("FAKE_CONNECT_FAIL"):
        fail(2, f'psql: error: connection to server at "{os.environ.get("PGHOST")}" (10.0.0.5), port 5432 failed: '
                f'FATAL:  password authentication failed for user "{os.environ.get("PGUSER")}" (tried {password()})')
    if sql == "select 1":
        print("1")
    elif sql == "show server_version_num":
        print(os.environ.get("FAKE_SERVER_NUM", "160004"))
    elif "information_schema.tables" in sql:
        print(os.environ.get("FAKE_TARGET_TABLE_COUNT", "0"))
    elif sql.startswith("select count(*) from"):
        state = os.environ.get("FAKE_STATE")
        restored = json.load(open(state)) if state and os.path.exists(state) else []
        name = sql.split("from", 1)[1].strip().replace('"', "")
        if name not in restored:
            fail(1, f'ERROR:  relation "{name}" does not exist')
        print("5")
    sys.exit(0)

if tool == "gpg":
    record()
    out = args[args.index("--output") + 1]
    src = args[-1]
    data = open(src, "rb").read()
    if "--encrypt" in args:
        open(out, "wb").write(b"GPGFAKE" + data[::-1])
    else:
        if not data.startswith(b"GPGFAKE"):
            fail(2, "gpg: decryption failed: No secret key")
        open(out, "wb").write(data[len(b"GPGFAKE"):][::-1])
    sys.exit(0)

fail(127, f"unknown fake tool {tool}")
