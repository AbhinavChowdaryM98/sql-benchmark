"""
Benchmark runner.

Two run modes controlled by config["use_hints"]:
  False (default) — sends bare query, no conversation_history
  True            — injects BIRD's evidence field as an assistant hint

Request payload (no hints):
  { "query": "...", "provider": "XAI", "conversation_history": [] }

Request payload (with hints):
  {
    "query": "...",
    "provider": "XAI",
    "conversation_history": [
      {
        "role": "assistant",
        "content": "Hint: price refers to the column unit_price. Use this when writing the query."
      }
    ]
  }

Response expected:
  {
    "sql_query": "SELECT ...",
    "response_time": 2.45,
    "token_usage": {
      "input_tokens": 50,
      "output_tokens": 25,
      "provider": "XAI",
      "model_name": "grok-beta"
    }
  }

Env vars:
  AGENT_URL        e.g. http://localhost:4747/sql-query
  AGENT_API_KEY    bearer token (optional)
  WORKERS          concurrent requests (default 4)
  USE_HINTS        true/false (default true)
  OUTPUT_CSV       path to results CSV
"""
import os
import time
import json
import re
import csv
import concurrent.futures
from pathlib import Path
import urllib.request
import urllib.error

from dotenv import load_dotenv
load_dotenv()

from downloader import load_questions, get_db_path, download_bird, DEFAULT_DATA_DIR
from evaluator import evaluate, clean_sql
from datasets import get_dataset_loader

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "agent_url": os.getenv("AGENT_URL", "http://localhost:4747/sql-query"),
    "agent_api_key": os.getenv("AGENT_API_KEY", ""),
    "provider": os.getenv("AGENT_PROVIDER", "XAI"),
    "workers": int(os.getenv("WORKERS", "4")),
    "output_csv": os.getenv("OUTPUT_CSV", "./results/benchmark_results.csv"),
    "data_dir": Path(os.getenv("BIRD_DATA_DIR", str(DEFAULT_DATA_DIR))),
    "use_hints": os.getenv("USE_HINTS", "true").lower() == "true",
    "use_qdrant_hints": os.getenv("USE_QDRANT_HINTS", "false").lower() == "true",
    "filter_db_ids": [],
    "filter_difficulties": [],
    "max_questions": int(os.getenv("MAX_QUESTIONS", "-1")),
    "request_timeout": int(os.getenv("REQUEST_TIMEOUT", "60")),
    "dataset": os.getenv("DATASET", "bird"),
}

COST_PER_1M_INPUT = 3.0
COST_PER_1M_OUTPUT = 15.0

FIELDNAMES = [
    "question_id", "db_id", "difficulty", "question", "evidence",
    "gold_sql", "predicted_sql",
    "execution_match", "exact_match", "f1", "precision", "recall",
    "gold_row_count", "pred_row_count",
    "gold_error", "pred_error", "agent_error",
    "latency_ms", "input_tokens", "output_tokens", "cost_usd",
    "provider", "model_name", "hints_used",
]

HINT_TEMPLATE = (
    "Hint: {evidence}. Use this context when writing the SQL query."
)

# ── Agent call ────────────────────────────────────────────────────────────────

def build_payload(question: str, evidence: str, config: dict, db_id: str = None, dataset_loader=None, dev_dir: Path = None) -> dict:
    # Use dataset-specific hint formatting
    if dataset_loader and config["use_hints"] and evidence:
        query_with_hints = dataset_loader.format_hints(question, evidence)
    else:
        query_with_hints = question

    payload = {
        "query": query_with_hints,
        "use_qdrant_hints": config.get("use_qdrant_hints", False),
    }
    
    # Add database info if available
    if dataset_loader and db_id and dev_dir:
        db_path = dataset_loader.get_db_path(dev_dir, db_id)
        db_type = dataset_loader.get_database_type()
        payload["db_id"] = db_id
        payload["db_type"] = db_type
        payload["db_path"] = str(db_path.absolute())
    elif db_id:
        payload["db_id"] = db_id
    
    if config.get("provider"):
        payload["provider"] = config["provider"]
    
    return payload


def call_agent(question: str, evidence: str, config: dict, db_id: str = None, dataset_loader=None, dev_dir: Path = None) -> dict:
    payload = json.dumps(build_payload(question, evidence, config, db_id, dataset_loader=dataset_loader, dev_dir=dev_dir)).encode()
    headers = {"Content-Type": "application/json"}
    if config["agent_api_key"]:
        headers["Authorization"] = f"Bearer {config['agent_api_key']}"

    req = urllib.request.Request(
        config["agent_url"], data=payload, headers=headers, method="POST"
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=config["request_timeout"]) as resp:
            wall_ms = (time.perf_counter() - t0) * 1000
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        wall_ms = (time.perf_counter() - t0) * 1000
        return _agent_error(f"HTTP {e.code}: {e.reason}", wall_ms)
    except Exception as e:
        wall_ms = (time.perf_counter() - t0) * 1000
        return _agent_error(str(e), wall_ms)

    usage = body.get("token_usage", {})
    agent_reported_ms = body.get("response_time", 0) * 1000
    latency_ms = agent_reported_ms if agent_reported_ms > 0 else wall_ms

    return {
        "sql": body.get("sql_query", ""),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "provider": usage.get("provider", ""),
        "model_name": usage.get("model_name", ""),
        "latency_ms": round(latency_ms, 1),
        "agent_error": None,
    }


def _agent_error(msg: str, latency_ms: float) -> dict:
    return {
        "sql": "", "input_tokens": 0, "output_tokens": 0,
        "provider": "", "model_name": "",
        "latency_ms": round(latency_ms, 1),
        "agent_error": msg,
    }


# ── Exact match ───────────────────────────────────────────────────────────────

def _normalize_sql(sql: str) -> str:
    sql = clean_sql(sql).lower()
    sql = re.sub(r"\s+", " ", sql).strip()
    return sql


def exact_match(gold_sql: str, predicted_sql: str) -> bool:
    return _normalize_sql(gold_sql) == _normalize_sql(predicted_sql)


# ── Per-question worker ───────────────────────────────────────────────────────

def run_question(q: dict, dev_dir: Path, config: dict, dataset_loader) -> dict:
    qid = q["question_id"]
    db_id = q["db_id"]
    question = q["question"]
    gold_sql = q["gold_sql"]
    difficulty = q["difficulty"]
    evidence = q.get("evidence", "")
    hints_used = config["use_hints"] and bool(evidence)

    try:
        db_path = str(dataset_loader.get_db_path(dev_dir, db_id))
    except FileNotFoundError as e:
        return _error_row(qid, db_id, question, evidence, gold_sql, difficulty, str(e), hints_used)

    agent_result = call_agent(question, evidence, config, db_id, dataset_loader, dev_dir)
    predicted_sql = agent_result["sql"]

    if predicted_sql and not agent_result["agent_error"]:
        eval_result = evaluate(db_path, gold_sql, predicted_sql)
        em = exact_match(gold_sql, predicted_sql)
    else:
        eval_result = {
            "execution_match": False, "f1": 0.0,
            "precision": 0.0, "recall": 0.0,
            "gold_row_count": None, "pred_row_count": None,
            "gold_error": None, "pred_error": agent_result["agent_error"],
        }
        em = False

    input_tok = agent_result["input_tokens"]
    output_tok = agent_result["output_tokens"]
    cost_usd = (input_tok / 1_000_000 * COST_PER_1M_INPUT) + \
               (output_tok / 1_000_000 * COST_PER_1M_OUTPUT)

    return {
        "question_id": qid,
        "db_id": db_id,
        "difficulty": difficulty,
        "question": question,
        "evidence": evidence,
        "gold_sql": gold_sql,
        "predicted_sql": predicted_sql,
        "execution_match": eval_result["execution_match"],
        "exact_match": em,
        "f1": eval_result["f1"],
        "precision": eval_result["precision"],
        "recall": eval_result["recall"],
        "gold_row_count": eval_result["gold_row_count"],
        "pred_row_count": eval_result["pred_row_count"],
        "gold_error": eval_result["gold_error"],
        "pred_error": eval_result["pred_error"],
        "agent_error": agent_result["agent_error"],
        "latency_ms": agent_result["latency_ms"],
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "cost_usd": round(cost_usd, 6),
        "provider": agent_result["provider"],
        "model_name": agent_result["model_name"],
        "hints_used": hints_used,
    }


def _error_row(qid, db_id, question, evidence, gold_sql, difficulty, error_msg, hints_used) -> dict:
    return {
        "question_id": qid, "db_id": db_id, "difficulty": difficulty,
        "question": question, "evidence": evidence,
        "gold_sql": gold_sql, "predicted_sql": "",
        "execution_match": False, "exact_match": False,
        "f1": 0.0, "precision": 0.0, "recall": 0.0,
        "gold_row_count": None, "pred_row_count": None,
        "gold_error": None, "pred_error": None, "agent_error": error_msg,
        "latency_ms": 0.0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        "provider": "", "model_name": "", "hints_used": hints_used,
    }


# ── Main runner ───────────────────────────────────────────────────────────────

def run_benchmark(config: dict = DEFAULT_CONFIG):
    data_dir = Path(config["data_dir"])
    dataset_loader = get_dataset_loader(config["dataset"])
    dev_dir = dataset_loader.download(data_dir)
    questions = dataset_loader.load_questions(dev_dir)

    if config.get("filter_db_ids"):
        questions = [q for q in questions if q["db_id"] in config["filter_db_ids"]]
    if config.get("filter_difficulties"):
        valid_difficulties = dataset_loader.get_difficulty_levels()
        requested_difficulties = config["filter_difficulties"]
        # Validate difficulty levels
        invalid_difficulties = [d for d in requested_difficulties if d not in valid_difficulties]
        if invalid_difficulties:
            print(f"[runner] Warning: Invalid difficulty levels for {dataset_loader.get_name()}: {invalid_difficulties}")
            print(f"[runner] Valid levels: {valid_difficulties}")
        questions = [q for q in questions if q["difficulty"] in config["filter_difficulties"]]
    max_questions = config.get("max_questions")
    if max_questions is not None and max_questions != -1:
        questions = questions[: max_questions]

    hint_label = "WITH hints" if config["use_hints"] else "WITHOUT hints"
    print(f"[runner] Dataset: {dataset_loader.get_name()}")
    print(f"[runner] Running {len(questions)} questions {hint_label} | workers={config['workers']}")
    print(f"[runner] Agent: {config['agent_url']}")

    output_path = Path(config["output_csv"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = []

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        writer.writeheader()

        with concurrent.futures.ThreadPoolExecutor(max_workers=config["workers"]) as executor:
            futures = {
                executor.submit(run_question, q, dev_dir, config, dataset_loader): q
                for q in questions
            }
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                writer.writerow(row)
                csvfile.flush()
                results.append(row)
                n = len(results)
                if n % 100 == 0 or n == len(questions):
                    em_rate = sum(r["execution_match"] for r in results) / n
                    print(f"[runner] {n}/{len(questions)} | exec_match={em_rate:.1%}")

    print(f"[runner] Done → {output_path}")
    return results


if __name__ == "__main__":
    run_benchmark()
