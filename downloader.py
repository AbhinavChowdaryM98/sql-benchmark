"""
Download and prepare BIRD-Bench dev set.
Source: https://huggingface.co/datasets/birdbench/bird
Falls back to local path if already downloaded.
"""
import json
import os
import zipfile
import urllib.request
from pathlib import Path

BIRD_DEV_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"
DEFAULT_DATA_DIR = Path("./bird_data")


def download_bird(data_dir: Path = DEFAULT_DATA_DIR, force: bool = False) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    zip_path = data_dir / "dev.zip"
    
    # Check for existing dev directory (could be dev or dev_YYYYMMDD)
    dev_dirs = [d for d in data_dir.iterdir() if d.is_dir() and d.name.startswith("dev")]
    if dev_dirs and not force:
        dev_dir = dev_dirs[0]  # Use the first dev directory found
        print(f"[downloader] BIRD dev set already at {dev_dir}, skipping download.")
        return dev_dir

    print(f"[downloader] Downloading BIRD-Bench dev set...")
    urllib.request.urlretrieve(BIRD_DEV_URL, zip_path)
    print(f"[downloader] Extracting...")
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
        print(f"[downloader] Extracting databases...")
        with zipfile.ZipFile(dev_databases_zip, "r") as zf:
            zf.extractall(dev_dir)

    print(f"[downloader] Done. Data at {dev_dir}")
    return dev_dir


def load_questions(dev_dir: Path) -> list[dict]:
    """
    Load BIRD dev questions JSON.
    Returns list of dicts with keys:
      question_id, db_id, question, SQL, difficulty
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

    print(f"[downloader] Loaded {len(questions)} questions across {len(set(q['db_id'] for q in questions))} DBs.")
    return questions


def get_db_path(dev_dir: Path, db_id: str) -> Path:
    """Resolve SQLite path for a given db_id."""
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


if __name__ == "__main__":
    dev_dir = download_bird()
    questions = load_questions(dev_dir)
    print(f"Sample: {questions[0]}")
