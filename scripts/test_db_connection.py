"""
Helper script to test database connectivity and PostGIS status on Aiven.
"""

import sys
from fifteen_minute_city.db.connection import check_db_connection


def main():
    print("Testing connection to Aiven PostgreSQL database...")
    try:
        result = check_db_connection()
        print("\n[SUCCESS] Database Connection Successful!")
        print(f"Status: {result['status']}")
        print(f"PostgreSQL Version: {result['postgres_version']}")
        print(f"PostGIS Version: {result['postgis_version']}")
    except Exception as e:
        print(f"\n[ERROR] Connection Failed: {e}", file=sys.stderr)
        print(
            "\nPlease ensure you have created a '.env' file in the project root with your Aiven DATABASE_URL.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
