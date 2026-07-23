"""
Utility script to clean and reset database tables on Aiven PostgreSQL.
"""

import sys
from sqlalchemy import text
from fifteen_minute_city.db.connection import get_db_engine


def reset_database():
    print("Resetting Aiven PostgreSQL database tables...")
    engine = get_db_engine()
    with engine.connect() as connection:
        # Truncate all application data tables and reset primary key identity sequences
        connection.execute(
            text(
                "TRUNCATE TABLE node_reachability, service, node, city_index, execution, category_osm_tag, service_category, city RESTART IDENTITY CASCADE;"
            )
        )
        connection.commit()
    print("[SUCCESS] Database tables truncated and sequence counters reset successfully!")


if __name__ == "__main__":
    reset_database()
