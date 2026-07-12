"""Storage dispatcher.

Picks the backend at import time: Snowflake when SNOWFLAKE_ACCOUNT is set,
DuckDB otherwise. Both expose the same contract (insert_activity,
insert_profile, replace_activity_points, snapshot_changed_count,
record_audit, query, conn, BACKEND), so nothing else in the app changes.
"""
import os

if os.environ.get("SNOWFLAKE_ACCOUNT"):
    from .db_snowflake import (  # noqa: F401
        BACKEND, DB_PATH, conn, insert_activity, insert_profile,
        query, record_audit, replace_activity_points, snapshot_changed_count,
    )
else:
    from .db_duckdb import (  # noqa: F401
        BACKEND, DB_PATH, conn, insert_activity, insert_profile,
        query, record_audit, replace_activity_points, snapshot_changed_count,
    )
