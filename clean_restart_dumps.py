import os
import sys
import time

from src import um_stash_extract_funcs as umstash

TARGET_MONTH_CODES = ("04", "07", "10")


def resolve_suites(suite_input, all_suites):
    # Resolve user input into a validated suite list.
    requested = suite_input.split()
    if not requested:
        raise ValueError("No suites provided")

    requested_lower = {item.lower() for item in requested}
    if "all" in requested_lower:
        return all_suites

    invalid = [suite for suite in requested if suite not in all_suites]
    if invalid:
        raise ValueError(f"These suites are not available: {' '.join(invalid)}")

    # Preserve user order while removing duplicates.
    seen = set()
    resolved = []
    for suite in requested:
        if suite not in seen:
            seen.add(suite)
            resolved.append(suite)
    return resolved


def dumps_dir_for_suite(suite):
    # Return absolute path to restart_dumps for a suite.
    return os.path.join(umstash.workspace_dir(), "Model_Output", suite, "restart_dumps")


def remove_target_dumps(dumps_dir):
    # Remove quarterly restart dump files matching *MM01_00 for MM in 04, 07, 10.
    removed = 0

    if not os.path.isdir(dumps_dir):
        print(f"Restart dumps directory not found: {dumps_dir}")
        return removed

    for month in TARGET_MONTH_CODES:
        matched = sorted(
            os.path.join(dumps_dir, name)
            for name in os.listdir(dumps_dir)
            if name.endswith(f"{month}01_00")
        )

        if not matched:
            print(f"No {month} files in dumps dir")
            continue

        print(f"Removing {month} files...")
        for path in matched:
            try:
                os.remove(path)
                removed += 1
            except FileNotFoundError:
                print(f"File not found: {path}")

    return removed


if __name__ == "__main__":
    suite_input = input(
        'Enter suite(s) (space-separated for multiple, or "all" for all suites): '
    ).strip()

    all_suites = umstash.available_suites()
    try:
        suites = resolve_suites(suite_input, all_suites)
    except ValueError as exc:
        print(f"Sorry, {exc}")
        sys.exit(1)

    print(" ", flush=True)
    print("Removing dump files...", flush=True)
    print(" ", flush=True)

    start_time = time.time()

    for suite in suites:
        print(f"Processing suite: {suite}", flush=True)
        print(" ", flush=True)

        dumps_dir = dumps_dir_for_suite(suite)
        files_removed = remove_target_dumps(dumps_dir)

        print(" ", flush=True)
        print(f"Files Removed: {files_removed}", flush=True)
        print(" ", flush=True)

    print(f"Time elapsed: {time.time() - start_time:.2f} s")
