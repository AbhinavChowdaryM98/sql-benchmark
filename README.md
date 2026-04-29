# SQL Benchmark Harness

Modular benchmarking framework for NL→SQL agents across multiple datasets (BIRD, Spider, etc.).

## Metrics

| Metric | Description |
|---|---|
| **Execution match** | F1 ≥ threshold over flattened result set values |
| **Exact match** | Normalized SQL string equality |
| **F1 / Precision / Recall** | Value overlap between gold and predicted result sets |
| **Latency p50/p95/p99** | End-to-end agent call latency in ms |
| **Token usage + cost** | Totals and per-question averages |

Results are broken down by difficulty tier (`simple` / `moderate` / `challenging`) and per-DB.

---

## Setup

```bash
pip install requests   # only stdlib used otherwise
```

No other dependencies. Uses Python's built-in `sqlite3`, `urllib`, `csv`, `concurrent.futures`.

**Note**: Dataset data (BIRD, Spider, etc.) is downloaded automatically on first run (~33GB for BIRD). The data directories are excluded from git via `.gitignore` to avoid committing large files.

---

## Agent API Contract

Your agent must expose a REST endpoint:

```
POST /sql-query
Content-Type: application/json

{
  "query": "How many employees are in the sales department?",
  "db_id": "employee_hire_evaluation",
  "provider": "XAI" // Optional, Unless the query generator has providers configured for SQL generation LLM
}
```

### With Hints (when USE_HINTS=true)

```
{
  "query": "How many employees are in the sales department?\n\nContext: The department column contains values like 'Sales', 'Engineering', 'Marketing'.",
  "db_id": "employee_hire_evaluation",
  "provider": "XAI" // Optional, Unless the query generator has providers configured for SQL generation LLM
}
```

Response:
```json
{
  "sql_query": "SELECT COUNT(*) FROM employees WHERE department = 'Sales'",
  "response_time": 2.45,
  "token_usage": {
    "input_tokens": 50,
    "output_tokens": 25,
    "provider": "XAI",
    "model_name": "grok-beta"
  }
}
```

`token_usage` is optional but recommended for cost tracking. If absent, token columns will be 0.

---

## Running

```bash
# Run BIRD benchmark (default)
python main.py run --dataset bird

# Run Spider benchmark
python main.py run --dataset spider

# With custom agent URL
python main.py run --agent-url http://localhost:4747/sql-query

# With more concurrency
python main.py run --workers 8

# With hints enabled (default)
python main.py run --hints

# Without hints
python main.py run

# Compare hints vs no-hints
python main.py run --compare

# Limited questions
python main.py run --max-questions 100

# Filter by difficulty (dataset-specific)
python main.py run --difficulties simple moderate

# Specific DBs
python main.py run --dbs california_schools debit_card_specialties

# Custom output path
python main.py run --output ./results/my_benchmark

# Recompute metrics from existing results CSV
python main.py metrics --csv ./results/benchmark_bird_no_hints.csv

# Compare two existing runs
python main.py compare --no-hints-csv ./results/benchmark_bird_no_hints.csv --hints-csv ./results/benchmark_bird_hints.csv
```

### Environment Variables

```bash
# Set dataset via environment variable
DATASET=spider python main.py run

# Set agent URL
AGENT_URL=http://localhost:4747/sql-query python main.py run

# Set workers
WORKERS=8 python main.py run

# Enable/disable hints
USE_HINTS=false python main.py run
```

---

## Output

```
results/
  benchmark_bird_no_hints.csv      # per-question results for BIRD
  benchmark_bird_hints.csv         # per-question results for BIRD with hints
  benchmark_spider_no_hints.csv    # per-question results for Spider
  benchmark_bird_no_hints_metrics.json  # aggregated stats
```

### Console summary

```
============================================================
SQL BENCHMARK REPORT - BIRD
============================================================

OVERALL
  Questions evaluated  : 12751
  Execution match      : 61.3%
  Exact match          : 12.4%
  Avg F1               : 0.7821
  Agent error rate     : 0.2%
  SQL exec error rate  : 8.1%

  Latency  p50=1240ms  p95=4820ms  p99=9100ms

  Tokens   in=14,823,100  out=412,600
  Cost     total=$55.6431  per_q=$0.004364

BY DIFFICULTY
  simple       exec=74.2%  exact=18.1%  f1=0.8432  n=4421
  moderate     exec=59.8%  exact=10.2%  f1=0.7601  n=5124
  challenging  exec=41.1%  exact=5.4%   f1=0.6190  n=3206
```

---

## Configuration

All config via env vars or CLI args:

| Env var | Default | Description |
|---|---|---|
| `DATASET` | `bird` | Dataset to benchmark (bird, spider) |
| `AGENT_URL` | `http://localhost:4747/sql-query` | Agent endpoint |
| `AGENT_API_KEY` | `` | Bearer token (optional) |
| `AGENT_PROVIDER` | `XAI` | Model provider |
| `WORKERS` | `4` | Concurrent requests |
| `OUTPUT_CSV` | `./results/benchmark_results.csv` | Results output |
| `BIRD_DATA_DIR` | `./bird_data` | Where to download dataset DBs |
| `USE_HINTS` | `true` | Include evidence hints in queries |
| `MAX_QUESTIONS` | `-1` | Limit number of questions (-1 = all) |

### Tuning execution match threshold

In `evaluator.py`:
```python
MATCH_THRESHOLD = 1.0  # lower to 0.8 for partial credit
```

### Tuning cost calculation

In `runner.py`:
```python
COST_PER_1M_INPUT = 3.0    # USD — update to your model
COST_PER_1M_OUTPUT = 15.0
```

---

## Supported Datasets

### BIRD-Bench

Downloaded automatically from the official BIRD repository on first run (~33.4GB).
Source: https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip

The data is downloaded to `./bird_data/` (configurable via `BIRD_DATA_DIR` env var). This directory is gitignored to avoid committing large files.

- **Questions**: 12,751 across 95 databases
- **Difficulty levels**: simple, moderate, challenging
- **Evidence**: Includes domain hints in the `evidence` field

### Spider 2.0

Placeholder implementation for Spider 2.0. Update the URL and data structure in `datasets/spider.py` when the official Spider 2.0 dataset is available.

The data will be downloaded to `./spider_data/` (configurable via data directory settings). This directory is gitignored.

- **Questions**: TBD
- **Difficulty levels**: easy, medium, hard, extra hard
- **Evidence**: May not include evidence field

---

## Adding New Datasets

To add support for a new dataset:

1. Create a new file in `datasets/` (e.g., `datasets/wikisql.py`)
2. Inherit from `DatasetLoader` base class
3. Implement the required methods:
   - `download(data_dir, force)` - Download/extract dataset
   - `load_questions(dev_dir)` - Load questions with metadata
   - `get_db_path(dev_dir, db_id)` - Resolve database paths
   - `format_hints(question, evidence)` - Format hints for agent
   - `get_difficulty_levels()` - Return valid difficulty levels
   - `get_name()` - Return dataset name
4. Add to `get_dataset_loader()` factory in `datasets/base.py`
5. Add to choices in `main.py` argument parser

Example:
```python
# datasets/wikisql.py
from .base import DatasetLoader
from pathlib import Path
from typing import List, Dict

class WikiSQLDatasetLoader(DatasetLoader):
    def download(self, data_dir: Path, force: bool = False) -> Path:
        # Download and extract WikiSQL dataset
        pass
    
    def load_questions(self, dev_dir: Path) -> List[Dict]:
        # Load WikiSQL questions
        pass
    
    def get_db_path(self, dev_dir: Path, db_id: str) -> Path:
        # Resolve database path
        pass
    
    def format_hints(self, question: str, evidence: str) -> str:
        # Format hints
        pass
    
    def get_difficulty_levels(self) -> List[str]:
        return ["easy", "hard"]
    
    def get_name(self) -> str:
        return "wikisql"
```

---

## BIRD-Bench Dataset Details

Each question includes `difficulty` (simple/moderate/challenging) and an optional `evidence` field (domain hints). When `USE_HINTS=true`, the evidence is included directly in the query text for better context.

## Architecture

```
sql-benchmark/
├── datasets/              # Dataset loaders
│   ├── __init__.py       # Module exports
│   ├── base.py           # Abstract DatasetLoader interface
│   ├── bird.py           # BIRD-Bench implementation
│   └── spider.py         # Spider 2.0 implementation
├── runner.py              # Benchmark runner (dataset-agnostic)
├── evaluator.py           # SQL execution evaluation
├── metrics.py             # Metrics computation
├── main.py                # CLI entry point
└── downloader.py          # Deprecated (use datasets module)
```

---

### Database Integration

For integration with custom database connectors:

```python
from db_integration import setup_sqlite_connector_env, list_available_databases

# List available databases
databases = list_available_databases()
print(f"Available databases: {databases}")

# Set up environment for your SQLiteConnector
setup_sqlite_connector_env("california_schools")

# Now your SQLiteConnector will work:
import os
connector = YourSQLiteConnector()  # Your custom connector
# os.environ["SQLITE_DB_PATH"] is set to the correct database path