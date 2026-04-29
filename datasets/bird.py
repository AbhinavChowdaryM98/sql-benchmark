"""
BIRD-Bench dataset loader implementation.

Source: https://huggingface.co/datasets/birdbench/bird
"""
import json
import os
import zipfile
import urllib.request
from pathlib import Path
from typing import List, Dict

from .base import DatasetLoader


class BirdDatasetLoader(DatasetLoader):
    """Dataset loader for BIRD-Bench."""

    BIRD_DEV_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"
    DIFFICULTY_LEVELS = ["simple", "moderate", "challenging"]

    def download(self, data_dir: Path, force: bool = False) -> Path:
        """
        Download and extract BIRD-Bench dev set.
        
        Args:
            data_dir: Directory to store the dataset
            force: Force re-download even if already present
            
        Returns:
            Path to the extracted dev directory
        """
        data_dir.mkdir(parents=True, exist_ok=True)
        zip_path = data_dir / "dev.zip"
        
        # Check for existing dev directory (could be dev or dev_YYYYMMDD)
        dev_dirs = [d for d in data_dir.iterdir() if d.is_dir() and d.name.startswith("dev")]
        if dev_dirs and not force:
            dev_dir = dev_dirs[0]  # Use the first dev directory found
            print(f"[bird] BIRD dev set already at {dev_dir}, skipping download.")
            return dev_dir

        print(f"[bird] Downloading BIRD-Bench dev set...")
        urllib.request.urlretrieve(self.BIRD_DEV_URL, zip_path)
        print(f"[bird] Extracting...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(data_dir)
        
        # Find the extracted dev directory
        dev_dirs = [d for d in data_dir.iterdir() if d.is_dir() and d.name.startswith("dev")]
        if not dev_dirs:
            raise FileNotFoundError("Could not find dev directory after extraction")
        
        dev_dir = dev_dirs[0]
        
        # Extract databases if dev_databases.zip exists
        dev_databases_zip = dev_dir / "dev_databases.zip"
        if dev_databases_zip.exists():
            print(f"[bird] Extracting databases...")
            with zipfile.ZipFile(dev_databases_zip, "r") as zf:
                zf.extractall(dev_dir)

        print(f"[bird] Done. Data at {dev_dir}")
        return dev_dir

    def load_questions(self, dev_dir: Path) -> List[Dict]:
        """
        Load BIRD dev questions JSON.
        
        Returns list of dicts with keys:
            question_id, db_id, question, SQL, difficulty, evidence
            
        Args:
            dev_dir: Path to the dataset directory
            
        Returns:
            List of question dictionaries
        """
        # Look for dev.json in the current directory structure
        json_path = dev_dir / "dev.json"
        if not json_path.exists():
            # Try to find it in subdirectories
            candidates = list(dev_dir.glob("**/dev.json"))
            if not candidates:
                raise FileNotFoundError(
                    f"Could not find dev questions JSON under {dev_dir}. "
                    "Check the BIRD download structure."
                )
            json_path = candidates[0]

        with open(json_path) as f:
            data = json.load(f)

        questions = []
        for item in data:
            questions.append({
                "question_id": item.get("question_id", item.get("id")),
                "db_id": item["db_id"],
                "question": item["question"],
                "gold_sql": item.get("SQL", item.get("query", "")),
                "difficulty": item.get("difficulty", "unknown"),
                "evidence": item.get("evidence", ""),  # BIRD provides extra hints
            })

        print(f"[bird] Loaded {len(questions)} questions across {len(set(q['db_id'] for q in questions))} DBs.")
        return questions

    def get_db_path(self, dev_dir: Path, db_id: str) -> Path:
        """
        Resolve SQLite path for a given db_id.
        
        Args:
            dev_dir: Path to the dataset directory
            db_id: Database identifier
            
        Returns:
            Path to the SQLite database file
        """
        # First check in dev_databases subdirectory (new BIRD structure)
        dev_databases_dir = dev_dir / "dev_databases"
        if dev_databases_dir.exists():
            candidates = list(dev_databases_dir.glob(f"{db_id}/{db_id}.sqlite"))
            if candidates:
                return candidates[0]
        
        # Fallback to original structure
        candidates = list(dev_dir.glob(f"**/{db_id}/{db_id}.sqlite")) + \
                     list(dev_dir.glob(f"**/{db_id}.sqlite"))
        if not candidates:
            raise FileNotFoundError(f"SQLite DB not found for db_id={db_id} under {dev_dir}")
        return candidates[0]

    def format_hints(self, question: str, evidence: str) -> str:
        """
        Format the question with BIRD evidence as hints.
        
        Args:
            question: The natural language question
            evidence: Hints/evidence from the dataset
            
        Returns:
            Formatted query string with hints
        """
        if evidence:
            return f"{question}\n\nHints: {evidence}"
        return question

    def get_difficulty_levels(self) -> List[str]:
        """
        Get the valid difficulty levels for BIRD.
        
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
        return "bird"
    
    def get_database_type(self) -> str:
        """
        Get the database type for BIRD.
        
        Returns:
            Database type (always "sqlite" for BIRD)
        """
        return "sqlite"
    
    def get_database_base_path(self, dev_dir: Path) -> Path:
        """
        Get the base directory containing all BIRD databases.
        
        Args:
            dev_dir: Path to the dataset directory
            
        Returns:
            Base path for databases
        """
        # BIRD stores databases in dev_databases subdirectory
        dev_databases_dir = dev_dir / "dev_databases"
        if dev_databases_dir.exists():
            return dev_databases_dir
        
        # Fallback to dataset root
        return dev_dir
