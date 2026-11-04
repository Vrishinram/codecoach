"""
Database Migration System for CodeCoach
Supports SQLite, PostgreSQL, and Turso (libsql) idempotently.
"""

import logging
from sqlalchemy import text, inspect
from app.database import engine

logger = logging.getLogger("codecoach.migrations")

def run_migrations():
    """
    Runs all pending migrations in sequential order.
    """
    logger.info("Checking database schema migrations...")
    with engine.begin() as conn:
        # Create migrations tracking table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(100) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Fetch already applied migrations
        result = conn.execute(text("SELECT version FROM schema_migrations;"))
        applied_versions = {row[0] for row in result.fetchall()}

        # Migration 001: Phase 1 Practice Features
        if "001_phase1_practice_tables" not in applied_versions:
            logger.info("Applying migration 001_phase1_practice_tables...")
            apply_migration_001(conn)
            conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version);"),
                {"version": "001_phase1_practice_tables"}
            )
            logger.info("Migration 001 applied successfully.")
        else:
            logger.info("Migration 001 already applied.")

def apply_migration_001(conn):
    """
    Creates tables for:
    - playground_snippets
    - coding_challenges
    - challenge_submissions
    - bug_hunt_scenarios
    - refactor_scenarios
    - output_predictor_scenarios
    """
    # 1. Playground Snippets
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS playground_snippets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_session_id VARCHAR(100),
            title VARCHAR(150) NOT NULL,
            code TEXT NOT NULL,
            csharp_version VARCHAR(20) DEFAULT '13.0',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

    # 2. Coding Challenges
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS coding_challenges (
            id VARCHAR(80) PRIMARY KEY,
            title VARCHAR(150) NOT NULL,
            difficulty VARCHAR(20) NOT NULL DEFAULT 'Beginner',
            topic_id VARCHAR(80) NOT NULL,
            description TEXT NOT NULL,
            starter_code TEXT NOT NULL,
            test_cases_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

    # 3. Challenge Submissions
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS challenge_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenge_id VARCHAR(80) NOT NULL,
            user_session_id VARCHAR(100),
            code TEXT NOT NULL,
            passed BOOLEAN DEFAULT FALSE,
            tests_passed INTEGER DEFAULT 0,
            tests_total INTEGER DEFAULT 0,
            execution_engine VARCHAR(30) DEFAULT 'piston',
            is_simulated BOOLEAN DEFAULT FALSE,
            stdout TEXT,
            stderr TEXT,
            feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

    # 4. Bug Hunt Scenarios
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS bug_hunt_scenarios (
            id VARCHAR(80) PRIMARY KEY,
            title VARCHAR(150) NOT NULL,
            difficulty VARCHAR(20) DEFAULT 'Beginner',
            topic_id VARCHAR(80) NOT NULL,
            description TEXT NOT NULL,
            code_snippet TEXT NOT NULL,
            buggy_lines_json TEXT NOT NULL,
            explanations_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

    # 5. Refactor Scenarios
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS refactor_scenarios (
            id VARCHAR(80) PRIMARY KEY,
            title VARCHAR(150) NOT NULL,
            topic_id VARCHAR(80) NOT NULL,
            description TEXT NOT NULL,
            bad_code TEXT NOT NULL,
            ideal_refactor TEXT NOT NULL,
            rubric_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

    # 6. Output Predictor Scenarios
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS output_predictor_scenarios (
            id VARCHAR(80) PRIMARY KEY,
            topic_id VARCHAR(80) NOT NULL,
            title VARCHAR(150) NOT NULL,
            code_snippet TEXT NOT NULL,
            options_json TEXT NOT NULL,
            correct_output TEXT NOT NULL,
            explanation TEXT NOT NULL,
            difficulty INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))
