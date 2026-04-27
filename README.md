# BIRD-Bench NL→SQL Benchmark Harness

Benchmarks your LangGraph-based NL→SQL agent against the BIRD-Bench dev set (12k questions, 95 DBs).

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
# Full benchmark (all 12k questions)
AGENT_URL=http://localhost:4747/sql-query python runner.py

# With more concurrency
AGENT_URL=http://localhost:4747/sql-query WORKERS=8 python runner.py

# With hints enabled (default)
USE_HINTS=true python runner.py

# Without hints
USE_HINTS=false python runner.py

# Limited questions
MAX_QUESTIONS=100 python runner.py

# Smoke test — 100 questions, simple only
python runner.py --max-questions 100 --difficulties simple

# Specific DBs
python runner.py --dbs california_schools debit_card_specialties

# Recompute metrics from existing results CSV
python metrics.py --csv ./results/benchmark_results.csv
```

---

## Output

```
results/
  benchmark_results.csv   # one row per question, all metrics
  metrics.json            # aggregated stats
```

### Console summary

```
============================================================
BIRD-BENCH BENCHMARK REPORT
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
| `AGENT_URL` | `http://localhost:4747/sql-query` | Agent endpoint |
| `AGENT_API_KEY` | `` | Bearer token (optional) |
| `AGENT_PROVIDER` | `XAI` | Model provider |
| `WORKERS` | `4` | Concurrent requests |
| `OUTPUT_CSV` | `./results/benchmark_results.csv` | Results output |
| `BIRD_DATA_DIR` | `./bird_data` | Where to download BIRD DBs |
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

## BIRD-Bench Dataset

Downloaded automatically from the official BIRD repository on first run (~33.4GB).
Source: https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip

Each question includes `difficulty` (simple/moderate/challenging) and an optional `evidence` field (domain hints). When `USE_HINTS=true`, the evidence is included directly in the query text for better context.

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
```