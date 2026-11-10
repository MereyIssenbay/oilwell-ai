"""Manage only the isolated workspace PostgreSQL cluster used by Phase 6."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/phase6"
DATA = LOCAL / "postgres"
CONFIG = LOCAL / "runtime.json"
PORT = 55436


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--bin-dir", type=Path, default=Path(os.environ.get(
        "OILWELL_POSTGRES_BIN", "C:/Program Files/PostgreSQL/18/bin")))
    args = parser.parse_args()
    suffix = ".exe" if os.name == "nt" else ""
    ctl = args.bin_dir / ("pg_ctl" + suffix)
    if not ctl.is_file():
        parser.error("PostgreSQL binaries not found; provide --bin-dir")
    # All cluster paths are fixed under this workspace. Never manage a system cluster.
    if not DATA.resolve().is_relative_to((ROOT / ".local").resolve()):
        parser.error("Workspace PostgreSQL directory escaped its boundary")
    if args.action != "start":
        if not (DATA / "PG_VERSION").is_file():
            parser.error("Workspace PostgreSQL has not been initialized")
        command = [str(ctl), "-D", str(DATA)]
        command += ["-m", "fast", "-w", "stop"] if args.action == "stop" else ["status"]
        return subprocess.run(command, check=False).returncode
    LOCAL.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        password = secrets.token_urlsafe(32)
        (LOCAL / "postgres-password.txt").write_text(password + "\n", encoding="utf-8")
        config = {"database_url": f"postgresql://oilwell_ai:{password}@127.0.0.1:{PORT}/oilwell_ai",
                  "postgres_bin": str(args.bin_dir), "postgres_data": str(DATA),
                  "api_host": "127.0.0.1", "api_port": 8000}
        CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo, conninfo_to_dict
    connection = conninfo_to_dict(config["database_url"])
    if connection.get("host") != "127.0.0.1" or connection.get("port") != str(PORT):
        raise ValueError("Local helper only initializes its fixed loopback PostgreSQL endpoint")
    if not (DATA / "PG_VERSION").exists():
        subprocess.run([str(args.bin_dir / ("initdb" + suffix)), "-D", str(DATA), "-U", "oilwell_ai",
                        "--encoding=UTF8", "--locale=C", "--auth-host=scram-sha-256",
                        "--auth-local=scram-sha-256", f"--pwfile={LOCAL / 'postgres-password.txt'}"], check=True)
    try:
        with psycopg.connect(make_conninfo(config["database_url"], dbname="postgres"), connect_timeout=3) as conn:
            actual = Path(conn.execute("SHOW data_directory").fetchone()[0]).resolve()
            if actual != DATA.resolve():
                raise ValueError("Loopback port belongs to a different PostgreSQL cluster")
        running = True
    except psycopg.OperationalError:
        running = False
    if not running:
        subprocess.run([str(ctl), "-D", str(DATA), "-l", str(LOCAL / "postgres.log"),
                        "-o", f"-h 127.0.0.1 -p {PORT} -c max_connections=20 -c shared_buffers=64MB",
                        "-t", "15", "-w", "start"], check=True)
    with psycopg.connect(make_conninfo(config["database_url"], dbname="postgres"), autocommit=True, connect_timeout=5) as conn:
        names = {"database_url": "oilwell_ai", "test_database_url": "oilwell_ai_test",
                 "qa_database_url": "oilwell_ai_qa", "integration_database_url": "oilwell_ai_integration"}
        for key, name in names.items():
            if conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone() is None:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            config[key] = make_conninfo(config["database_url"], dbname=name)
    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Workspace PostgreSQL ready on 127.0.0.1:{PORT}; credentials remain in ignored local configuration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
