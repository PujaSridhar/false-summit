"""Run this once after filling the Snowflake vars in .env — it verifies the
connection, the database/warehouse, and that Time Travel is queryable.

    .venv/bin/python scripts/check_snowflake.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# load .env if present (no dependency on python-dotenv)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    for line in open(env_path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

if not os.environ.get("SNOWFLAKE_ACCOUNT"):
    print("✗ SNOWFLAKE_ACCOUNT not set. Fill in the Snowflake vars in .env first.")
    sys.exit(1)

print(f"Connecting to account '{os.environ['SNOWFLAKE_ACCOUNT']}' as "
      f"'{os.environ.get('SNOWFLAKE_USER')}' ...")

try:
    from backend import db_snowflake as sf
    ver = sf.query("SELECT current_version()")[0][0]
    db = sf.query("SELECT current_database(), current_warehouse()")[0]
    print(f"✓ Connected. Snowflake {ver}")
    print(f"✓ Database={db[0]}  Warehouse={db[1]}")
    # prove Time Travel is available on the freshly-created table
    sf.query("SELECT count(*) FROM trackpoints AT(OFFSET => -1)")
    print("✓ Time Travel query accepted (AT(OFFSET => -1)).")
    print("\nAll good — set SNOWFLAKE_ACCOUNT in your shell/.env and the game "
          "will use Snowflake automatically. Level 5 now runs on real Time Travel.")
except Exception as e:
    print(f"✗ Failed: {e}")
    print("\nCommon fixes:")
    print("  - account identifier is ORG-ACCOUNT (e.g. mgjdbba-ip54391), no https://")
    print("  - if MFA blocks the password login, generate a key-pair or a")
    print("    Programmatic Access Token and use that as SNOWFLAKE_PASSWORD")
    print("  - make sure you ran the CREATE DATABASE / CREATE WAREHOUSE SQL")
    sys.exit(1)
