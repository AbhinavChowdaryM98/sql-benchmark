"""
Aggregate benchmark results from CSV.

Outputs:
  - Overall execution match, exact match, avg F1
  - Breakdown by difficulty tier (simple / moderate / challenging)
  - Breakdown by DB
  - Latency p50, p95, p99
  - Token usage and cost totals + per-question averages
"""
import csv
import json
import statistics
from pathlib import Path
from collections import defaultdict


def load_results(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            # Cast types
            row["execution_match"] = row["execution_match"] == "True"
            row["exact_match"] = row["exact_match"] == "True"
            row["f1"] = float(row["f1"] or 0)
            row["precision"] = float(row["precision"] or 0)
            row["recall"] = float(row["recall"] or 0)
            row["latency_ms"] = float(row["latency_ms"] or 0)
            row["input_tokens"] = int(row["input_tokens"] or 0)
            row["output_tokens"] = int(row["output_tokens"] or 0)
            row["cost_usd"] = float(row["cost_usd"] or 0)
            rows.append(row)
    return rows


def _pct(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * p / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def _tier_stats(rows: list[dict]) -> dict:
    if not rows:
        return {}
    latencies = [r["latency_ms"] for r in rows if r["latency_ms"] > 0]
    return {
        "count": len(rows),
        "execution_match_rate": round(sum(r["execution_match"] for r in rows) / len(rows), 4),
        "exact_match_rate": round(sum(r["exact_match"] for r in rows) / len(rows), 4),
        "avg_f1": round(statistics.mean(r["f1"] for r in rows), 4),
        "avg_precision": round(statistics.mean(r["precision"] for r in rows), 4),
        "avg_recall": round(statistics.mean(r["recall"] for r in rows), 4),
        "agent_error_rate": round(sum(1 for r in rows if r["agent_error"]) / len(rows), 4),
        "pred_sql_error_rate": round(sum(1 for r in rows if r["pred_error"]) / len(rows), 4),
        "latency_p50_ms": round(_pct(latencies, 50), 1),
        "latency_p95_ms": round(_pct(latencies, 95), 1),
        "latency_p99_ms": round(_pct(latencies, 99), 1),
        "total_input_tokens": sum(r["input_tokens"] for r in rows),
        "total_output_tokens": sum(r["output_tokens"] for r in rows),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "avg_cost_usd_per_question": round(
            sum(r["cost_usd"] for r in rows) / len(rows), 6
        ),
    }


def compute_metrics(csv_path: str) -> dict:
    rows = load_results(csv_path)
    if not rows:
        return {"error": "No results found"}

    # Overall
    overall = _tier_stats(rows)

    # By difficulty
    by_difficulty = {}
    difficulty_groups = defaultdict(list)
    for r in rows:
        difficulty_groups[r["difficulty"]].append(r)
    for diff, group in sorted(difficulty_groups.items()):
        by_difficulty[diff] = _tier_stats(group)

    # By DB (top 20 worst performing for quick debugging)
    db_groups = defaultdict(list)
    for r in rows:
        db_groups[r["db_id"]].append(r)
    db_stats = {}
    for db_id, group in db_groups.items():
        db_stats[db_id] = {
            "count": len(group),
            "execution_match_rate": round(
                sum(r["execution_match"] for r in group) / len(group), 4
            ),
            "avg_f1": round(statistics.mean(r["f1"] for r in group), 4),
        }
    # Sort by execution_match_rate ascending (worst first)
    worst_dbs = dict(
        sorted(db_stats.items(), key=lambda x: x[1]["execution_match_rate"])[:20]
    )

    return {
        "overall": overall,
        "by_difficulty": by_difficulty,
        "worst_20_dbs": worst_dbs,
        "total_questions": len(rows),
    }


def print_report(metrics: dict, hint_label: str = ""):
    print("\n" + "=" * 60)
    header = "BIRD-BENCH BENCHMARK REPORT"
    if hint_label:
        header += f" — {hint_label}"
    print(header)
    print("=" * 60)

    o = metrics["overall"]
    print(f"\n{'OVERALL':}")
    print(f"  Questions evaluated  : {metrics['total_questions']}")
    print(f"  Execution match      : {o['execution_match_rate']:.1%}")
    print(f"  Exact match          : {o['exact_match_rate']:.1%}")
    print(f"  Avg F1               : {o['avg_f1']:.4f}")
    print(f"  Agent error rate     : {o['agent_error_rate']:.1%}")
    print(f"  SQL exec error rate  : {o['pred_sql_error_rate']:.1%}")
    print(f"\n  Latency  p50={o['latency_p50_ms']}ms  p95={o['latency_p95_ms']}ms  p99={o['latency_p99_ms']}ms")
    print(f"\n  Tokens   in={o['total_input_tokens']:,}  out={o['total_output_tokens']:,}")
    print(f"  Cost     total=${o['total_cost_usd']:.4f}  per_q=${o['avg_cost_usd_per_question']:.6f}")

    print(f"\n{'BY DIFFICULTY':}")
    for diff, stats in metrics["by_difficulty"].items():
        print(
            f"  {diff:<12} exec={stats['execution_match_rate']:.1%}  "
            f"exact={stats['exact_match_rate']:.1%}  "
            f"f1={stats['avg_f1']:.4f}  "
            f"n={stats['count']}"
        )

    print(f"\n{'WORST 20 DBs (by exec match)':}")
    for db_id, stats in metrics["worst_20_dbs"].items():
        print(
            f"  {db_id:<35} exec={stats['execution_match_rate']:.1%}  "
            f"f1={stats['avg_f1']:.4f}  n={stats['count']}"
        )
    print("=" * 60)


def save_metrics_json(metrics: dict, output_path: str = "./results/metrics.json"):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[metrics] Saved to {output_path}")


if __name__ == "__main__":
    import sys
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "./results/benchmark_results.csv"
    metrics = compute_metrics(csv_path)
    print_report(metrics)
    save_metrics_json(metrics)
