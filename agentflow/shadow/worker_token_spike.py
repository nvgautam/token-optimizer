import json
from pathlib import Path
from collections import defaultdict


def compute_worker_mean_tokens(log_path: str, calib_path: str) -> dict:
    """
    Compute mean worker session tokens from task token log.

    Reads task_token_log.jsonl, groups by task_id, sums token_deltas per task.
    Filters to tasks with >= 3 entries (noise filter).
    Returns mean across filtered tasks.

    Args:
        log_path: Path to task_token_log.jsonl
        calib_path: Path to calibration file (unused in this function, present for API)

    Returns:
        {
            "worker_mean_tokens": float,
            "sample_count": int,
            "task_ids": list[str]
        }
    """
    result = {
        "worker_mean_tokens": 0.0,
        "sample_count": 0,
        "task_ids": []
    }

    log_file = Path(log_path)
    if not log_file.exists():
        return result

    # Read and group by task_id
    task_tokens = defaultdict(list)
    task_entry_counts = defaultdict(int)

    try:
        with open(log_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    task_id = entry.get("task_id")
                    token_delta = entry.get("token_delta")
                    if task_id is not None and token_delta is not None:
                        task_tokens[task_id].append(token_delta)
                        task_entry_counts[task_id] += 1
                except (json.JSONDecodeError, ValueError):
                    continue
    except (IOError, OSError):
        return result

    if not task_tokens:
        return result

    # Sum tokens per task and filter tasks with >= 3 entries
    task_sums = []
    filtered_task_ids = []

    for task_id in sorted(task_tokens.keys()):
        if task_entry_counts[task_id] >= 3:
            total_tokens = sum(task_tokens[task_id])
            task_sums.append(total_tokens)
            filtered_task_ids.append(task_id)

    if not task_sums:
        return result

    # Compute mean
    worker_mean = sum(task_sums) / len(task_sums)

    return {
        "worker_mean_tokens": worker_mean,
        "sample_count": len(task_sums),
        "task_ids": filtered_task_ids
    }


def update_calibration_file(log_path: str, calib_path: str) -> None:
    """
    Update calibration file with worker_mean_tokens field.

    Reads calibration JSON, computes worker mean, merges field atomically.

    Args:
        log_path: Path to task_token_log.jsonl
        calib_path: Path to calibration JSON file
    """
    # Compute worker mean
    result = compute_worker_mean_tokens(log_path, calib_path)
    worker_mean = result["worker_mean_tokens"]

    # Read existing calibration
    calib_file = Path(calib_path)
    existing_cal = {}

    if calib_file.exists():
        try:
            with open(calib_file, "r") as f:
                existing_cal = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Merge worker_mean_tokens
    existing_cal["worker_mean_tokens"] = worker_mean

    # Write atomically: write to temp, then rename
    try:
        calib_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = Path(str(calib_file) + ".tmp")
        with open(temp_file, "w") as f:
            json.dump(existing_cal, f, indent=2)
        temp_file.replace(calib_file)
    except (IOError, OSError):
        pass


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute worker mean token consumption from task log."
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update calibration JSON with worker_mean_tokens field",
    )
    args = parser.parse_args()

    log_path = str(Path.home() / ".agentflow" / "task_token_log.jsonl")
    calib_path = str(Path.home() / ".agentflow" / "rate_calibration_claude.json")

    result = compute_worker_mean_tokens(log_path, calib_path)
    print(json.dumps(result))

    if args.update:
        update_calibration_file(log_path, calib_path)
