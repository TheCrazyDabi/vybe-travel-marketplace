#!/usr/bin/env python3
"""Supabase Managed PostgreSQL Migration Utility for VYBE.

Transfers schema and data from local SQLite database to Supabase PostgreSQL:
1. Validates connection strings and normalizes dialect for psycopg 3.
2. Creates all tables on the target PostgreSQL database (preserving schema integrity).
3. Transfers table records in topological dependency order to satisfy foreign keys.
4. Resets PostgreSQL primary key sequences (setval) to prevent sequence collisions.

Usage:
  python scripts/migrate_to_supabase.py --target "postgresql+psycopg://postgres.[ref]:[pass]@[host]:6543/postgres"
  python scripts/migrate_to_supabase.py --target-env SUPABASE_DATABASE_URL
  python scripts/migrate_to_supabase.py --dry-run
"""

import argparse
import logging
import os
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import Config
from models import (
    Booking,
    CompanionMessage,
    Conversation,
    CustomOffer,
    Enquiry,
    Interest,
    Message,
    PackItem,
    Quotation,
    Report,
    AuditEvent,
    DeviceToken,
    Notification,
    Review,
    Stop,
    StopActivity,
    TravelCompany,
    TravelerProfile,
    TravelPackage,
    TripDay,
    TripPlan,
    User,
    UserPreference,
    VerificationRecord,
    db,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_to_supabase")

# Ordered model list respecting foreign key hierarchies
MIGRATION_MODELS = [
    User,
    TravelerProfile,
    UserPreference,
    TravelCompany,
    VerificationRecord,
    TravelPackage,
    Interest,
    Conversation,
    Message,
    Report,
    Enquiry,
    Quotation,
    Booking,
    TripPlan,
    TripDay,
    Stop,
    StopActivity,
    PackItem,
    CompanionMessage,
    CustomOffer,
    Review,
    Notification,
    DeviceToken,
    AuditEvent,
]


def normalize_postgres_uri(uri: str) -> str:
    """Ensure PostgreSQL URI uses SQLAlchemy 2.x psycopg dialect."""
    if uri.startswith("postgres://"):
        return uri.replace("postgres://", "postgresql+psycopg://", 1)
    if uri.startswith("postgresql://") and not uri.startswith("postgresql+"):
        return uri.replace("postgresql://", "postgresql+psycopg://", 1)
    return uri


def get_sqlite_uri() -> str:
    """Resolve source SQLite database URI."""
    default_db = os.path.join(BASE_DIR, "instance", "vybe.db")
    if os.path.exists(default_db):
        return f"sqlite:///{default_db}"
    return Config.SQLALCHEMY_DATABASE_URI


def run_migration(source_uri: str, target_uri: str, dry_run: bool = False):
    logger.info("Initializing migration...")
    logger.info("Source: %s", source_uri)
    # Mask password in log output
    masked_target = target_uri
    if "@" in target_uri and "://" in target_uri:
        prefix, rest = target_uri.split("://", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        masked_target = f"{prefix}://{user}:*****@{host}"
    logger.info("Target: %s (dry_run=%s)", masked_target, dry_run)

    # 1. Connect to source
    source_engine = create_engine(source_uri)
    SourceSession = sessionmaker(bind=source_engine)
    source_session = SourceSession()
    source_inspector = inspect(source_engine)

    if dry_run:
        logger.info("[Dry Run] Inspecting source tables...")
        for model in MIGRATION_MODELS:
            tname = model.__tablename__
            if source_inspector.has_table(tname):
                count = source_session.query(model).count()
                logger.info("  Table '%s': %d records to migrate", tname, count)
            else:
                logger.info("  Table '%s': not found in source", tname)
        logger.info("[Dry Run] Completed inspection. No changes made.")
        return

    # 2. Connect to target PostgreSQL
    target_engine = create_engine(target_uri, pool_pre_ping=True)
    TargetSession = sessionmaker(bind=target_engine)
    target_session = TargetSession()

    # 3. Create schema tables on target if missing
    logger.info("Ensuring all tables exist on target PostgreSQL database...")
    from app import create_app
    app = create_app()
    with app.app_context():
        # Bind db metadata to target engine
        db.metadata.create_all(bind=target_engine)
    logger.info("Schema tables created/verified successfully.")

    # 4. Copy records table by table
    total_migrated = 0
    for model in MIGRATION_MODELS:
        tname = model.__tablename__
        if not source_inspector.has_table(tname):
            continue

        records = source_session.query(model).all()
        if not records:
            continue

        logger.info("Migrating %d records for '%s'...", len(records), tname)
        for r in records:
            # Read columns as dict
            col_data = {col.name: getattr(r, col.name) for col in model.__table__.columns}
            # Check if record with same PK already exists on target
            pk_col = model.__table__.primary_key.columns.values()[0].name
            pk_val = col_data.get(pk_col)

            existing = target_session.query(model).filter(getattr(model, pk_col) == pk_val).first() if pk_val else None
            if not existing:
                new_inst = model(**col_data)
                target_session.add(new_inst)

        target_session.commit()
        total_migrated += len(records)

        # 5. Reset PostgreSQL auto-increment sequence for serial primary keys
        try:
            target_session.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{tname}', 'id'), coalesce(max(id), 1)) FROM {tname};"
            ))
            target_session.commit()
        except Exception as seq_err:
            # SQLite or tables without 'id' sequence might not support this; ignore gracefully
            target_session.rollback()

    logger.info("Migration complete! Total %d records synchronized into Supabase PostgreSQL.", total_migrated)


def main():
    parser = argparse.ArgumentParser(description="Migrate VYBE SQLite data to Supabase Managed PostgreSQL")
    parser.add_argument("--source", default=None, help="Source database URI (defaults to instance/vybe.db)")
    parser.add_argument("--target", default=None, help="Target PostgreSQL database URI")
    parser.add_argument("--target-env", default="SUPABASE_DATABASE_URL", help="Env variable containing target URI")
    parser.add_argument("--dry-run", action="store_true", help="Inspect source without writing to target")

    args = parser.parse_args()

    source_uri = args.source or get_sqlite_uri()

    if args.dry_run:
        run_migration(source_uri, "sqlite:///:memory:", dry_run=True)
        return

    target_uri = args.target or os.environ.get(args.target_env) or os.environ.get("DATABASE_URL")
    if not target_uri or "sqlite" in target_uri:
        logger.error("Error: A valid PostgreSQL connection URI must be supplied via --target or %s", args.target_env)
        logger.error("Example: python scripts/migrate_to_supabase.py --target postgresql+psycopg://postgres.[ref]:[pass]@[host]:6543/postgres")
        sys.exit(1)

    target_uri = normalize_postgres_uri(target_uri)
    run_migration(source_uri, target_uri, dry_run=False)


if __name__ == "__main__":
    main()
