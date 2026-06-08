import os
import shutil
import sys
import time

import numpy as np

from src import um_stash_extract_funcs as umstash


def get_output_dirs(suite_path, cycles):
    # Return cycle subdirectories whose year code is in cycles.
    output_dirs = []
    for d in os.listdir(suite_path):
        if "T0000Z" in d and os.path.isdir(os.path.join(suite_path, d)):
            year_code = d[:4]
            if year_code in cycles:
                output_dirs.append(d)
    return output_dirs


def expected_files_for_cycle(cycle_dir, suite, fids):
    # Build list of expected pp filenames for a given cycle directory and set of file IDs.
    suite_code = suite.split("-")[-1][:5]
    file_list = []
    match cycle_dir[4:6]:
        case "01": mon_codes = np.arange(1, 4)
        case "04": mon_codes = np.arange(4, 7)
        case "07": mon_codes = np.arange(7, 10)
        case "10": mon_codes = np.arange(10, 13)
    for fid in fids:
        file_list.extend([
            f"{suite_code}a.{fid}{cycle_dir[:4]}{month:02d}01.pp"
            for month in mon_codes
        ])
    return file_list


def move_missing_files(suite, suite_path, output_dirs, start_year, end_year):
    # Search all cycle directories for pp files that belong in output_dirs but are misplaced.
    fids = umstash.read_stash_table(suite, start_year, end_year)["OUTPUT_FILE"].unique()
    all_dirs = [d for d in os.listdir(suite_path) if os.path.isdir(os.path.join(suite_path, d))]
    for out_dir in output_dirs:
        print(f"\n{out_dir}:")
        out_dir_path = os.path.join(suite_path, out_dir)
        expected_files = expected_files_for_cycle(out_dir, suite, fids)
        for fname in expected_files:
            if os.path.exists(os.path.join(out_dir_path, fname)):
                continue
            found = False
            for other_dir in all_dirs:
                if other_dir == out_dir:
                    continue
                other_dir_path = os.path.join(suite_path, other_dir)
                src_file = os.path.join(other_dir_path, fname)
                if os.path.exists(src_file):
                    found = True
                    dst_file = os.path.join(out_dir_path, fname)
                    if not os.path.exists(dst_file):
                        shutil.move(src_file, dst_file)
                        print(f"Moved {fname} from {other_dir_path} to {out_dir_path}")
                    break
            if not found:
                print(
                    f"WARNING: {fname} expected in {out_dir_path} "
                    f"not found in any other output directory for {suite}"
                )


def rename_p1_files(suite_path, output_dirs):
    # Rename all p1 files to pm within the requested cycle directories.
    # Also checks the cycle directory immediately after the requested range to catch
    # any overflow p1 files written to the next cycle by the last requested cycle.
    all_dirs = sorted(
        d for d in os.listdir(suite_path) if os.path.isdir(os.path.join(suite_path, d))
    )
    last_dir = output_dirs[-1]
    try:
        last_idx = all_dirs.index(last_dir)
        if last_idx + 1 < len(all_dirs):
            dirs_to_rename = output_dirs + [all_dirs[last_idx + 1]]
        else:
            dirs_to_rename = output_dirs
    except ValueError:
        dirs_to_rename = output_dirs

    for out_dir in dirs_to_rename:
        print(f"\n{out_dir}:")
        out_dir_path = os.path.join(suite_path, out_dir)
        for file in os.listdir(out_dir_path):
            if "p1" in file:
                old_path = os.path.join(out_dir_path, file)
                new_path = os.path.join(out_dir_path, file.replace("p1", "pm"))
                os.rename(old_path, new_path)
                print(f"Renamed {old_path} to {new_path}")


def move_restart_dumps(suite_path, output_dirs):
    # Move restart dump files (.da files ending in _00) to suite_path/restart_dumps/.
    restart_dir = os.path.join(suite_path, "restart_dumps")
    os.makedirs(restart_dir, exist_ok=True)
    for out_dir in output_dirs:
        out_dir_path = os.path.join(suite_path, out_dir)
        for file in os.listdir(out_dir_path):
            if file.endswith("_00") and ".da" in file:
                src = os.path.join(out_dir_path, file)
                dst = os.path.join(restart_dir, file)
                shutil.move(src, dst)
                print(f"Moved restart dump {file} to {restart_dir}")


def delete_checksums(suite_path):
    # Delete any checksum files found anywhere under suite_path.
    for root, dirs, files in os.walk(suite_path):
        for file in files:
            if "checksums" in file:
                os.remove(os.path.join(root, file))
                print(f"Deleted checksum file {file} in {root}")


if __name__ == "__main__":
    suite = input("Enter suite: ").strip()
    all_suites = umstash.available_suites()
    if suite not in all_suites:
        print(f"Invalid suite: {suite}. Available suites: {', '.join(all_suites)}")
        sys.exit(1)

    min_yr, max_yr = umstash.suite_available_years(suite)
    print(f"Years available for suite {suite}: {min_yr} - {max_yr}")

    try:
        start_year, end_year = umstash.validate_whole_year_block(
            input("Enter start year: "),
            input("Enter end year: "),
            min_yr=min_yr,
            max_yr=max_yr,
        )
    except ValueError as exc:
        print(f"Invalid year range: {exc}")
        sys.exit(1)

    print(" ")

    cycles = {str(year) for year in range(start_year, end_year)}
    start_time = time.time()

    suite_path = os.path.join(umstash.workspace_dir(), "Model_Output", suite)
    output_dirs = get_output_dirs(suite_path, cycles)
    print(f"Processing suite {suite}...")

    print(" ")
    print("-" * 30)
    print(" ")

    print("Renaming any p1 files to pm...")
    rename_p1_files(suite_path, output_dirs)

    print(" ")
    print("-" * 30)
    print(" ")

    print("Moving missing files to the correct directories...")
    move_missing_files(suite, suite_path, output_dirs, start_year, end_year)

    print(" ")
    print("-" * 30)
    print(" ")

    print("Moving restart dumps...\n")
    move_restart_dumps(suite_path, output_dirs)

    print(" ")
    print("-" * 30)
    print(" ")

    print("Deleting any checksum files...\n")
    delete_checksums(suite_path)

    print(" ")
    print("-" * 30)
    print(" ")

    print(f"Finished processing suite {suite}")
    print(f"Total time elapsed: {(time.time() - start_time):.2f} s")
