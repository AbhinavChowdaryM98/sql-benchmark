"""
Entry point for BIRD-Bench harness.

Usage:
  # Baseline only (no hints)
  python main.py run

  # With hints only
  python main.py run --hints

  # Both runs + side-by-side comparison (recommended)
  python main.py run --compare

  # Smoke test
  python main.py run --compare --max-questions 100 --difficulties simple

  # Recompute metrics from existing CSVs
  python main.py metrics --csv ./results/benchmark_results.csv
  python main.py compare --no-hints-csv ./results/no_hints.csv --hints-csv ./results/hints.csv
"""
import argparse
from pathlib import Path

from runner import run_benchmark, DEFAULT_CONFIG
from metrics import compute_metrics, print_report, save_metrics_json
from datasets import get_dataset_loader


def _build_config(args, use_hints: bool, output_suffix: str) -> dict:
    import os
    config = dict(DEFAULT_CONFIG)
    if args.agent_url:
        config["agent_url"] = args.agent_url
    if args.workers:
        config["workers"] = args.workers
    if getattr(args, "max_questions", None):
        config["max_questions"] = args.max_questions
    if getattr(args, "difficulties", None):
        config["filter_difficulties"] = args.difficulties
    elif os.getenv("DIFFICULTIES"):
        config["filter_difficulties"] = os.getenv("DIFFICULTIES").split()
    if getattr(args, "dbs", None):
        config["filter_db_ids"] = args.dbs
    elif os.getenv("DBS"):
        config["filter_db_ids"] = os.getenv("DBS").split()
    if getattr(args, "data_dir", None):
        config["data_dir"] = Path(args.data_dir)
    if getattr(args, "dataset", None):
        config["dataset"] = args.dataset

    config["use_hints"] = use_hints
    base = getattr(args, "output", None) or os.getenv("OUTPUT", "./results/benchmark")
    base = base.rstrip(".csv")
    dataset_name = config.get("dataset", "bird")
    config["output_csv"] = f"{base}_{dataset_name}_{output_suffix}.csv"
    return config


def _run_single(args, use_hints: bool):
    suffix = "hints" if use_hints else "no_hints"
    config = _build_config(args, use_hints, suffix)
    run_benchmark(config)
    metrics = compute_metrics(config["output_csv"])
    print_report(metrics, hint_label="WITH hints" if use_hints else "WITHOUT hints")
    save_metrics_json(metrics, config["output_csv"].replace(".csv", "_metrics.json"))
    return metrics, config["output_csv"]


def cmd_run(args):
    import os
    compare = getattr(args, "compare", False)
    hints_only = getattr(args, "hints", False)

    # Get default hints setting from env var
    use_hints_default = os.getenv("USE_HINTS", "true").lower() == "true"

    if compare:
        metrics_no, csv_no = _run_single(args, use_hints=False)
        metrics_yes, csv_yes = _run_single(args, use_hints=True)
        print_comparison(metrics_no, metrics_yes)
    elif hints_only:
        _run_single(args, use_hints=True)
    else:
        _run_single(args, use_hints=use_hints_default)


def cmd_metrics(args):
    csv_path = args.csv or "./results/benchmark_no_hints.csv"
    metrics = compute_metrics(csv_path)
    print_report(metrics)
    save_metrics_json(metrics, csv_path.replace(".csv", "_metrics.json"))


def cmd_compare(args):
    m_no = compute_metrics(args.no_hints_csv)
    m_yes = compute_metrics(args.hints_csv)
    print_report(m_no, hint_label="WITHOUT hints")
    print_report(m_yes, hint_label="WITH hints")
    print_comparison(m_no, m_yes)


def print_comparison(m_no: dict, m_yes: dict):
    o_no = m_no["overall"]
    o_yes = m_yes["overall"]

    def delta(key):
        d = o_yes[key] - o_no[key]
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.1%}" if isinstance(d, float) and d < 10 else f"{sign}{d:.4f}"

    print("\n" + "=" * 60)
    print("HINTS vs NO-HINTS COMPARISON")
    print("=" * 60)
    print(f"{'Metric':<28} {'No hints':>10} {'With hints':>10} {'Delta':>10}")
    print("-" * 60)

    rows = [
        ("Execution match", "execution_match_rate"),
        ("Exact match", "exact_match_rate"),
        ("Avg F1", "avg_f1"),
        ("Agent error rate", "agent_error_rate"),
        ("SQL exec error rate", "pred_sql_error_rate"),
        ("Latency p50 (ms)", "latency_p50_ms"),
        ("Latency p95 (ms)", "latency_p95_ms"),
        ("Cost per question ($)", "avg_cost_usd_per_question"),
    ]

    for label, key in rows:
        v_no = o_no.get(key, 0)
        v_yes = o_yes.get(key, 0)
        d = v_yes - v_no
        if isinstance(v_no, float) and v_no <= 1.0 and key.endswith("rate"):
            fmt = lambda v: f"{v:.1%}"
            dfmt = f"{'+'if d>=0 else ''}{d:.1%}"
        elif isinstance(v_no, float):
            fmt = lambda v: f"{v:.4f}"
            dfmt = f"{'+'if d>=0 else ''}{d:.4f}"
        else:
            fmt = lambda v: f"{v:.1f}"
            dfmt = f"{'+'if d>=0 else ''}{d:.1f}"
        print(f"  {label:<26} {fmt(v_no):>10} {fmt(v_yes):>10} {dfmt:>10}")

    print("\nBY DIFFICULTY")
    print(f"  {'Tier':<12} {'No hints exec':>14} {'Hints exec':>12} {'Delta':>8}")
    print("  " + "-" * 50)
    # Get all unique difficulty levels from both metrics
    all_difficulties = set()
    all_difficulties.update(m_no["by_difficulty"].keys())
    all_difficulties.update(m_yes["by_difficulty"].keys())
    for diff in sorted(all_difficulties):
        no = m_no["by_difficulty"].get(diff, {}).get("execution_match_rate", 0)
        yes = m_yes["by_difficulty"].get(diff, {}).get("execution_match_rate", 0)
        d = yes - no
        print(f"  {diff:<12} {no:>14.1%} {yes:>12.1%} {'+'if d>=0 else ''}{d:.1%}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="SQL benchmark harness for multiple datasets (BIRD, Spider, etc.)")
    sub = parser.add_subparsers(dest="command")

    # Shared args
    def add_common(p):
        p.add_argument("--agent-url")
        p.add_argument("--workers", type=int)
        p.add_argument("--max-questions", type=int)
        p.add_argument("--dataset", choices=["bird", "spider"], default="bird", help="Dataset to benchmark (default: bird)")
        p.add_argument("--difficulties", nargs="+", help="Difficulty levels to filter (dataset-specific)")
        p.add_argument("--dbs", nargs="+")
        p.add_argument("--output", help="Base path for output CSVs (suffix _no_hints/_hints added)")
        p.add_argument("--data-dir")

    run_p = sub.add_parser("run", help="Run benchmark")
    add_common(run_p)
    mode = run_p.add_mutually_exclusive_group()
    mode.add_argument("--hints", action="store_true", help="Run with hints only")
    mode.add_argument("--compare", action="store_true", help="Run both and compare")

    metrics_p = sub.add_parser("metrics", help="Compute metrics from CSV")
    metrics_p.add_argument("--csv")

    compare_p = sub.add_parser("compare", help="Compare two existing CSVs")
    compare_p.add_argument("--no-hints-csv", required=True)
    compare_p.add_argument("--hints-csv", required=True)

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "metrics":
        cmd_metrics(args)
    elif args.command == "compare":
        cmd_compare(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
