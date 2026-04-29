"""
Spider 2.0 dataset loader implementation.

Source: https://github.com/taoyds/spider
Note: This is a placeholder implementation for Spider 2.0.
You may need to adjust URLs and data structure based on the actual Spider 2.0 release.
"""
import json
import os
import zipfile
import urllib.request
from pathlib import Path
from typing import List, Dict

from .base import DatasetLoader


class SpiderDatasetLoader(DatasetLoader):
    """Dataset loader for Spider 1.0."""

    # Official Spider dataset Google Drive URL
    SPIDER_DATASET_URL = "https://drive.google.com/uc?export=download&id=1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J"
    DIFFICULTY_LEVELS = ["easy", "medium", "hard", "extra hard"]

    def download(self, data_dir: Path, force: bool = False) -> Path:
        """
        Download and extract Spider 1.0 dataset with databases.
        
        Note: Google Drive downloads require manual intervention.
        
        Args:
            data_dir: Directory to store the dataset
            force: Force re-download even if already present
            
        Returns:
            Path to the extracted dataset directory
        """
        data_dir.mkdir(parents=True, exist_ok=True)
        spider_dir = data_dir / "spider"
        
        # Check if spider directory already exists and has databases
        if spider_dir.exists() and (spider_dir / "database").exists() and not force:
            print(f"[spider] Spider dataset already at {spider_dir}, skipping download.")
            return spider_dir

        print(f"[spider] Spider 1.0 dataset requires manual download:")
        print(f"[spider] 1. Visit: https://drive.google.com/file/d/1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J")
        print(f"[spider] 2. Download the 'spider.zip' file")
        print(f"[spider] 3. Extract it to: {data_dir}")
        print(f"[spider] 4. Ensure the extracted directory is named 'spider'")
        print(f"[spider]")
        print(f"[spider] Expected structure after extraction:")
        print(f"[spider] {data_dir}")
        print(f"[spider]   spider/")
        print(f"[spider]     database/")
        print(f"[spider]       academic/")
        print(f"[spider]         academic.sqlite")
        print(f"[spider]       aircraft/")
        print(f"[spider]         aircraft.sqlite")
        print(f"[spider]       ... (more database directories)")
        print(f"[spider]     dev.json")
        print(f"[spider]     train.json")
        print(f"[spider]     tables.json")
        
        raise FileNotFoundError(
            f"Spider dataset not found. Please download manually from the URL above "
            f"and extract to {spider_dir}"
        )

    def load_questions(self, dev_dir: Path) -> List[Dict]:
        """
        Load Spider 2.0 questions JSON.
        
        Spider typically uses a different JSON structure than BIRD.
        This implementation assumes a structure similar to the original Spider dataset.
        
        Returns list of dicts with keys:
            question_id, db_id, question, SQL, difficulty, evidence
            
        Args:
            dev_dir: Path to the dataset directory
            
        Returns:
            List of question dictionaries
        """
        # Spider typically has dev.json in a specific location
        # Try common locations
        json_paths = [
            dev_dir / "dev.json",
            dev_dir / "spider" / "dev.json",
            dev_dir / "data" / "dev.json",
        ]
        
        json_path = None
        for path in json_paths:
            if path.exists():
                json_path = path
                break
        
        if not json_path:
            # Try to find it in subdirectories
            candidates = list(dev_dir.glob("**/dev.json"))
            if not candidates:
                raise FileNotFoundError(
                    f"Could not find dev questions JSON under {dev_dir}. "
                    "Check the Spider download structure."
                )
            json_path = candidates[0]

        with open(json_path) as f:
            data = json.load(f)

        questions = []
        for item in data:
            # Spider JSON structure may vary - adjust as needed
            questions.append({
                "question_id": item.get("question_id", item.get("id")),
                "db_id": item.get("db_id", item.get("database_id")),
                "question": item.get("question", item.get("query")),
                "gold_sql": item.get("SQL", item.get("query", item.get("sql", ""))),
                "difficulty": item.get("difficulty", "unknown"),
                "evidence": item.get("evidence", ""),  # Spider may not have evidence
            })

        print(f"[spider] Loaded {len(questions)} questions across {len(set(q['db_id'] for q in questions))} DBs.")
        return questions

    def get_db_path(self, dev_dir: Path, db_id: str) -> Path:
        """
        Resolve SQLite path for a given db_id in Spider dataset.
        
        Spider stores databases in database/{db_id}/{db_id}.sqlite structure.
        
        Args:
            dev_dir: Path to the dataset directory
            db_id: Database identifier
            
        Returns:
            Path to the SQLite database file
        """
        # Spider stores databases in database/{db_id}/{db_id}.sqlite
        db_dir = dev_dir / "database"
        if db_dir.exists():
            # Try subdirectory structure: database/{db_id}/{db_id}.sqlite
            sub_dir = db_dir / db_id
            db_path = sub_dir / f"{db_id}.sqlite"
            if db_path.exists():
                return db_path
            
            # Try direct file match: database/{db_id}.sqlite
            direct_path = db_dir / f"{db_id}.sqlite"
            if direct_path.exists():
                return direct_path
        
        # Fallback to recursive search
        candidates = list(dev_dir.glob(f"**/{db_id}.sqlite"))
        if candidates:
            return candidates[0]
        
        raise FileNotFoundError(
            f"Spider database not found for db_id='{db_id}'. "
            f"Expected at: {db_dir / f'{db_id}/{db_id}.sqlite'} or {db_dir / f'{db_id}.sqlite'}"
        )

    def format_hints(self, question: str, evidence: str) -> str:
        """
        Format the question with Spider evidence as hints.
        
        Spider typically doesn't provide evidence like BIRD, so this
        implementation just returns the question as-is.
        
        Args:
            question: The natural language question
            evidence: Hints/evidence from the dataset (usually empty for Spider)
            
        Returns:
            Formatted query string with hints
        """
        if evidence:
            return f"{question}\n\nContext: {evidence}"
        return question

    def get_difficulty_levels(self) -> List[str]:
        """
        Get the valid difficulty levels for Spider.
        
        Spider's difficulty levels may differ from BIRD.
        
        Returns:
            List of difficulty level strings
        """
        return self.DIFFICULTY_LEVELS

    def get_name(self) -> str:
        """
        Get the dataset name.
        
        Returns:
            Dataset name
        """
        return "spider"
    
    def get_database_type(self) -> str:
        """
        Get the database type for Spider.
        
        Returns:
            Database type (always "sqlite" for Spider)
        """
        return "sqlite"
    
    def get_database_base_path(self, dev_dir: Path) -> Path:
        """
        Get the base directory containing all Spider databases.
        
        Args:
            dev_dir: Path to the dataset directory
            
        Returns:
            Base path for databases
        """
        # Spider typically stores databases in a 'database' or 'databases' directory
        db_dirs = [
            dev_dir / "database",
            dev_dir / "databases",
            dev_dir / "spider" / "database",
            dev_dir / "data" / "database",
        ]
        
        for db_dir in db_dirs:
            if db_dir.exists():
                return db_dir
        
        # Fallback to dataset root
        return dev_dir
