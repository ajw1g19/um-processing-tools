import os
import subprocess
import sys

import src.um_stash_extract_funcs as umstash
from src.pp_check_utils import iso, load_state, newest_pp_time, state_write, write_sbatch_pp_check

ROOT_DIR = umstash._root_dir()
STATE_PATH = os.path.join(ROOT_DIR, "config", "pp_check_state.json")
SBATCH_DIR = os.path.join(ROOT_DIR, "run", "sbatch_scripts")
LOG_DIR = os.path.join(ROOT_DIR, "run", "logs")


def main():
    state = load_state(STATE_PATH)
    suites = umstash.available_suites()

    to_submit = []
    for suite in suites:
        suite_dir = os.path.join(umstash.workspace_dir(), "Model_Output", suite)
        if not os.path.isdir(suite_dir):
            print(f"{suite}: suite directory not found, skipping")
            continue

        newest = newest_pp_time(suite_dir)
        suite_state = state.get(suite)
        stored = suite_state.get("mtime") if isinstance(suite_state, dict) else None

        if newest is None:
            print(f"{suite}: no .pp files found")
            continue

        if stored is None or newest > stored:
            stored_str = iso(stored) if stored is not None else "None"
            print(f"{suite}: NEW files detected (newest mtime {iso(newest)} > stored {stored_str})")
            to_submit.append((suite, stored or 0.0, newest))
        else:
            print(f"{suite}: no new files detected (newest mtime {iso(newest)} <= stored {iso(stored)})")

    if not to_submit:
        print("No suites with new files detected. Exiting.")
        sys.exit(0)

    print("\nThe following sbatch jobs will be submitted:")
    for suite, stored_ts, _ in to_submit:
        sbatch_file = os.path.join(SBATCH_DIR, f"{suite}_pp_check.sbatch")
        logfile = os.path.join(LOG_DIR, f"{suite}_pp_check.%j.out")
        print(f"  {suite}: SINCE={stored_ts}  sbatch -> {sbatch_file}  log -> {logfile}")

    ans = input("\nProceed to submit these jobs to slurm? [y/n] ").strip().lower()
    if ans not in ("y", "yes"):
        print("Aborting: no jobs submitted")
        sys.exit(0)

    os.makedirs(SBATCH_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    for suite, stored_ts, newest_ts in to_submit:
        sbatch_file = os.path.join(SBATCH_DIR, f"{suite}_pp_check.sbatch")
        logfile = os.path.join(LOG_DIR, f"{suite}_pp_check.%j.out")
        write_sbatch_pp_check(sbatch_file, suite, stored_ts, logfile)

        proc = subprocess.run(
            ["sbatch", sbatch_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.returncode == 0:
            print(f"Submitted sbatch for {suite}: {proc.stdout.strip()}")
            state[suite] = {"mtime": newest_ts, "mtime_iso": iso(newest_ts)}
        else:
            print(f"Failed to submit sbatch for {suite}: rc={proc.returncode}, output={proc.stdout.strip()}")

    state_write(STATE_PATH, state)
    print("State updated and written")


if __name__ == "__main__":
    main()
