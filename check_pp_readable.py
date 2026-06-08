import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from src import um_stash_extract_funcs as umstash
from src.pp_check_utils import iso, load_pp_check_config, load_state, newest_pp_time, state_write

STATE_PATH = os.path.join(umstash._root_dir(), "config", "pp_check_state.json")

TERMINAL_STATUSES = {"FAILED", "CANCELED", "INACTIVE", "UNKNOWN"}


# --- PP file discovery ---


def find_pp_files(suite_path):
    # Return sorted list of all .pp files directly under suite_path cycle subdirectories.
    import glob
    pattern = os.path.join(suite_path, "*", "*.pp")
    return sorted(glob.glob(pattern))


# --- cf readability check ---


def try_read_pp(path, timeout=300, max_retries=3, retry_delay=30):
    # Attempt to cf.read the file in a subprocess to isolate any cf crashes from the pool.
    # Returns (path, True, None) on success, (path, False, error_str) on failure.
    helper = (
        "import cf,sys,traceback\n"
        "p = sys.argv[1]\n"
        "try:\n"
        "    f = cf.read(p)\n"
        "    if not f:\n"
        "        print('CF_READ_EMPTY')\n"
        "        sys.exit(2)\n"
        "    sys.exit(0)\n"
        "except Exception:\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )

    cmd = [sys.executable, "-c", helper, path]

    for attempt in range(1, max_retries + 1):
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
            )
            out = (proc.stdout or "").strip()
            if proc.returncode == 0:
                return (path, True, None)
            if proc.returncode == 2 or "CF_READ_EMPTY" in out:
                return (path, False, "cf.read returned empty")
            return (path, False, f"cf.read helper failed (rc={proc.returncode}): {out}")

        except subprocess.TimeoutExpired:
            if attempt < max_retries:
                time.sleep(retry_delay)
                continue
            return (path, False, f"cf.read TIMEOUT after {timeout}s ({attempt} attempts)")

        except Exception as exc:
            return (path, False, f"subprocess error: {exc}")


# --- Globus helpers ---


def globus_transfer_paths(suite, dst_file, archer2_archive_base):
    # Construct Globus src path on ARCHER2 and confirm dst path on JASMIN for a pp file.
    # dst_file should be the absolute path on JASMIN.
    src_base = f"{archer2_archive_base}/{suite}"
    fn = os.path.basename(dst_file)
    dst_mon = fn[-7:-5]

    if dst_mon in ("12", "01", "02"):
        src_mon = "01"
    elif dst_mon in ("03", "04", "05"):
        src_mon = "04"
    elif dst_mon in ("06", "07", "08"):
        src_mon = "07"
    else:
        src_mon = "10"

    year = fn[-11:-7]
    if dst_mon == "12":
        year = str(int(year) + 1)

    return f"{src_base}/{year}{src_mon}01T0000Z/{fn}", dst_file


def submit_globus_transfer(src_path, dst_path, archer2_id, jasmin_id, label=None, timeout=300):
    # Submit a Globus transfer task and return (task_id, error_str).
    label = label or f"transfer {os.path.basename(dst_path)}"
    cmd = [
        "globus", "transfer",
        f"{archer2_id}:{src_path}",
        f"{jasmin_id}:{dst_path}",
        "--label", label,
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None, "globus transfer CLI timed out"
    out = proc.stdout or ""
    if proc.returncode != 0:
        return None, f"globus transfer failed (rc={proc.returncode}): {out.strip()}"
    m = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", out
    )
    if m:
        return m.group(0), None
    return None, f"no task id found in globus output: {out.strip()}"


def get_task_status_cli(task_id, timeout=60):
    # Query a Globus task status; returns (status_str, fatal_error_str) or (None, error_msg).
    cmd = ["globus", "task", "show", task_id, "--format", "json"]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None, "globus task show timed out"
    try:
        data = json.loads(proc.stdout)
    except Exception:
        return None, f"could not parse globus output: {proc.stdout.strip()}"
    return data.get("status"), data.get("fatal_error")


def find_active_incoming_transfers(suite, timeout=60):
    # Return True if any active Globus task has a label containing suite, False otherwise.
    cmd = ["globus", "task", "list", "--limit", "50", "--format", "json"]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout
        )
        data = json.loads(proc.stdout)
    except Exception:
        return False
    for task in data.get("DATA", []):
        if task.get("status") == "ACTIVE" and suite in (task.get("label") or ""):
            return True
    return False


def wait_for_incoming_transfers(suite, poll_interval=60):
    # Block until no active Globus transfers referencing suite are detected.
    while True:
        if not find_active_incoming_transfers(suite):
            print(
                f"No active incoming Globus transfers for {suite}, proceeding with .pp checks...",
                flush=True,
            )
            return
        print(
            f"Detected active incoming Globus transfers for {suite}: "
            f"waiting {poll_interval} s...",
            flush=True,
        )
        time.sleep(poll_interval)


# --- Main ---


def main():
    p = argparse.ArgumentParser(
        description="Check all .pp files for a suite are readable by cf.read, "
                    "and re-fetch any unreadable files from ARCHER2 via Globus."
    )
    p.add_argument("suite", help="Suite name (directory under Model_Output), e.g. u-dd727")
    p.add_argument("--workers", "-w", type=int, default=8,
                   help="Number of parallel workers (default 8)")
    p.add_argument("--root", default="Model_Output",
                   help="Root Model_Output directory (default ./Model_Output)")
    p.add_argument("--since", type=float, default=None,
                   help="Only check files with mtime >= this epoch timestamp")
    args = p.parse_args()

    cfg = load_pp_check_config()
    archer2_id = cfg["globus"]["archer2_endpoint"]
    jasmin_id = cfg["globus"]["jasmin_endpoint"]
    archer2_archive_base = cfg["globus"]["archer2_archive_base"]

    suite_path = os.path.join(args.root, args.suite)
    if not os.path.isdir(suite_path):
        raise SystemExit(f"Suite path not found: {suite_path}")

    wait_for_incoming_transfers(args.suite)

    files = find_pp_files(suite_path)
    if not files:
        print("No .pp files found under", suite_path)
        return

    since = args.since if args.since is not None else 0.0
    before_count = len(files)
    files = [f for f in files if os.path.getmtime(f) >= since]
    print(f"Filtering files by mtime >= {since} (kept {len(files)}/{before_count})", flush=True)

    start = time.time()
    unreadable = []
    timeout_files = []
    total = len(files)
    print(f"Checking {total} files using {args.workers} workers...", flush=True)

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(try_read_pp, f): f for f in files}
        for i, fut in enumerate(as_completed(futures), 1):
            path = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:
                ok, err = False, f"Executor error: {exc}"
            else:
                if res is None:
                    ok, err = False, "Worker returned None"
                else:
                    path, ok, err = res

            if not ok:
                if isinstance(err, str) and "TIMEOUT" in err.upper():
                    timeout_files.append(path)
                    print(f"TIMEOUT: {path} -> {err}", flush=True)
                else:
                    unreadable.append((path, err))
                    print(f"\nUNREADABLE: {path}\n{err}\n", flush=True)

            if (i % 10 == 0) or (i == total):
                print(f"Processed {i}/{total} in {time.time() - start:.1f}s", flush=True)

    elapsed = time.time() - start
    good = total - len(unreadable) - len(timeout_files)
    print("-" * 60, flush=True)
    print(
        f"Done in {elapsed:.1f}s — readable: {good}, "
        f"unreadable: {len(unreadable)}, timeout: {len(timeout_files)}",
        flush=True,
    )

    if timeout_files:
        print(f"\nRe-processing {len(timeout_files)} TIMEOUT files...", flush=True)
        re_unreadable = []
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(try_read_pp, f): f for f in timeout_files}
            for fut in as_completed(futures):
                fpath = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:
                    re_unreadable.append((fpath, f"Executor error on retry: {exc}"))
                    print(f"UNREADABLE on retry: {fpath} -> Executor error: {exc}", flush=True)
                    continue
                if not res:
                    re_unreadable.append((fpath, "Worker returned None on retry"))
                    print(f"UNREADABLE on retry: {fpath} -> Worker returned None", flush=True)
                    continue
                _, ok, err = res
                if ok:
                    print(f"Now readable after retry: {fpath}", flush=True)
                else:
                    re_unreadable.append((fpath, err))
                    print(f"\nUNREADABLE on retry: {fpath}\n{err}\n", flush=True)

        unreadable.extend(re_unreadable)
        print(f"After retry: additional unreadable: {len(re_unreadable)}", flush=True)

    if not unreadable:
        print("No unreadable files — exiting.", flush=True)
        return

    print("\nList of unreadable files:", flush=True)
    for path, _ in unreadable:
        print(path, flush=True)

    tasks = {}
    for path, _ in unreadable:
        src_path, dst_path = globus_transfer_paths(args.suite, path, archer2_archive_base)
        label = f"{args.suite} missing {os.path.basename(dst_path)}: ARCHER2 -> JASMIN"
        task_id, err = submit_globus_transfer(src_path, dst_path, archer2_id, jasmin_id, label=label)
        if task_id:
            tasks[task_id] = dst_path
            print(f"Submitted transfer for {dst_path} -> task {task_id}", flush=True)
        else:
            print(f"Failed to submit transfer for {dst_path}: {err}", flush=True)

    if not tasks:
        print("No transfers were submitted (all failed)", flush=True)
        return

    pending_tasks = dict(tasks)
    while pending_tasks:
        print(f"\nPolling {len(pending_tasks)} transfer tasks...", flush=True)
        finished_this_round = []
        for task_id, dst in list(pending_tasks.items()):
            status, fatal = get_task_status_cli(task_id)
            if status is None:
                print(fatal, flush=True)
                continue
            print(f"Task {task_id} status: {status}", flush=True)

            if status == "SUCCEEDED":
                print(f"Task SUCCEEDED for file: {dst}", flush=True)
                finished_this_round.append(task_id)
            elif status in TERMINAL_STATUSES:
                print(f"Task {task_id} ended with {status} for file: {dst}", flush=True)
                finished_this_round.append(task_id)

        for tid in finished_this_round:
            pending_tasks.pop(tid, None)
        if pending_tasks:
            time.sleep(60)

    print("\nAll transfer tasks finished", flush=True)

    print("\nChecking readability of transferred files...", flush=True)
    for path, _ in unreadable:
        res = try_read_pp(path, max_retries=1)
        if not res:
            print(f"UNREADABLE on retry: {path} -> Worker returned None", flush=True)
            continue
        _, ok, err = res
        if ok:
            print(f"Now readable after transfer: {path}", flush=True)
        else:
            print(f"\nUNREADABLE after transfer: {path}\n{err}\n", flush=True)

    try:
        newest = newest_pp_time(suite_path)
        if newest is not None:
            state = load_state(STATE_PATH)
            state[args.suite] = {"mtime": newest, "mtime_iso": iso(newest)}
            state_write(STATE_PATH, state)
            print(
                f"\nState updated: wrote newest mtime {iso(newest)} "
                f"for suite {args.suite} to {STATE_PATH}",
                flush=True,
            )
        else:
            print(f"\nNo .pp files found to update state for {args.suite}", flush=True)
    except Exception as exc:
        print(f"\nFailed to update state file: {exc}", flush=True)


if __name__ == "__main__":
    main()
