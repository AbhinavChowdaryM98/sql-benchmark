"""
Database integration utilities for external connectors.

This module provides easy access to SQLite database paths
for integration with custom database connectors like SQLiteConnector.
"""

import os
from pathlib import Path
from downloader import download_bird, load_questions, get_db_path, DEFAULT_DATA_DIR

def get_all_database_paths(data_dir: Path = DEFAULT_DATA_DIR) -> dict[str, Path]:
    """
    Get all available database paths from the BIRD benchmark.
    
    Returns:
        dict: Mapping of db_id to database file paths
    """
    dev_dir = download_bird(data_dir)
    questions = load_questions(dev_dir)
    
    # Get unique database IDs
    db_ids = set(q["db_id"] for q in questions)
    
    # Get paths for all databases
    db_paths = {}
    for db_id in db_ids:
        try:
            db_path = get_db_path(dev_dir, db_id)
            db_paths[db_id] = db_path
        except FileNotFoundError:
            print(f"Warning: Database not found for db_id={db_id}")
    
    return db_paths

def get_database_path(db_id: str, data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    """
    Get the path for a specific database.
    
    Args:
        db_id: Database identifier
        data_dir: Data directory path
        
    Returns:
        Path: Database file path
    """
    dev_dir = download_bird(data_dir)
    return get_db_path(dev_dir, db_id)

def setup_sqlite_connector_env(db_id: str, data_dir: Path = DEFAULT_DATA_DIR):
    """
    Set up environment variable for SQLiteConnector.
    
    Args:
        db_id: Database identifier to use
        data_dir: Data directory path
    """
    db_path = get_database_path(db_id, data_dir)
    os.environ["SQLITE_DB_PATH"] = str(db_path)
    print(f"Set SQLITE_DB_PATH to: {db_path}")

def list_available_databases(data_dir: Path = DEFAULT_DATA_DIR) -> list[str]:
    """
    List all available database IDs.
    
    Args:
        data_dir: Data directory path
        
    Returns:
        list: Available database IDs
    """
    dev_dir = download_bird(data_dir)
    questions = load_questions(dev_dir)
    return sorted(set(q["db_id"] for q in questions))

# Example usage
if __name__ == "__main__":
    print("Available databases:")
    for db_id in list_available_databases():
        print(f"  - {db_id}")
    
    # Example: Set up for a specific database
    db_id = list_available_databases()[0] if list_available_databases() else None
    if db_id:
        print(f"\nSetting up environment for database: {db_id}")
        setup_sqlite_connector_env(db_id)
        
        # Now you can use your SQLiteConnector
        # from your_connector import SQLiteConnector
        # connector = SQLiteConnector()
        # schemas = connector.get_all_schemas()
