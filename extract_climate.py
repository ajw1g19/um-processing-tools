# Submit climate extraction jobs for a predefined package list across one time window.
# Writes YAML extraction configs and sbatch scripts within STASH_extract/run.

import os
import subprocess
import sys

import pandas as pd
import yaml

from src import um_stash_extract_funcs as umstash

ROOT_DIR = os.path.dirname(__file__)
RUN_DIR = os.path.join(ROOT_DIR, "run")
CONFIG_DIR = os.path.join(RUN_DIR, "stash_extract")
SBATCH_DIR = os.path.join(RUN_DIR, "sbatch_scripts")
LOG_DIR = os.path.join(RUN_DIR, "logs")

for path in [CONFIG_DIR, SBATCH_DIR, LOG_DIR]:
    os.makedirs(path, exist_ok=True)


suite = input("Enter suite: ").strip()
all_suites = umstash.available_suites()
if suite not in all_suites:
    print("Sorry, that suite is not available. Try again...")
    sys.exit(1)

suite_min_yr, suite_max_yr = umstash.suite_available_years(suite)
print(f"Years available for suite {suite}: {suite_min_yr} - {suite_max_yr}")
first_yr_input = input("Please enter the start year: ").strip()
last_yr_input = input("Please enter the last year (exclusive): ").strip()

try:
    first_yr, last_yr = umstash.validate_whole_year_block(
        first_yr_input,
        last_yr_input,
        min_yr=suite_min_yr,
        max_yr=suite_max_yr,
    )
except ValueError as exc:
    print(f"Invalid year range: {exc}")
    sys.exit(1)

stash_lookup = umstash.read_stash_table(suite, first_yr, last_yr)
package_names = umstash.extract_climate_packages()

print(" ")
print("-" * 50)
print(" ")

extract_configs = []
for package_name in package_names:
    stash_package = umstash.um_stash_package(package_name, suite, first_yr, last_yr)
    if not stash_package:
        print(f"Skipping package '{package_name}': package is unavailable for this suite/version")
        continue

    stash_extract = stash_lookup.iloc[:0, :].copy()
    for stash in stash_package:
        code_entry = stash_lookup[
            (stash_lookup["SECTION"] == stash["SECTION"])
            & (stash_lookup["ITEM"] == stash["ITEM"])
            & (stash_lookup["OUTPUT_FILE"] == stash["OUTPUT_FILE"])
            & (stash_lookup["DOMAIN"] == stash["DOMAIN"])
        ]
        stash_extract = pd.concat([stash_extract, code_entry])

    if stash_extract.empty:
        print(f"Skipping package '{package_name}': no matching records found in STASH table")
        continue

    print(f"The following STASH requests will be extracted for package: {package_name}")
    print(" ")
    print(stash_extract.reset_index(drop=True))
    print(" ")
    input("Press Enter to continue...")
    print(" ")

    stash_extract_norm = stash_extract.copy()
    stash_extract_norm["SECTION"] = (
        stash_extract_norm["SECTION"].astype(str).str.lstrip("0").replace("", "0")
    )
    stash_extract_norm["ITEM"] = (
        stash_extract_norm["ITEM"].astype(str).str.lstrip("0").replace("", "0")
    )

    config_file = os.path.join(
        CONFIG_DIR, f"{suite}_{package_name}_{first_yr}_{last_yr}.yaml"
    )
    config = {
        "suite": suite,
        "package_name": package_name,
        "start_year": int(first_yr),
        "end_year": int(last_yr),
        "stash_requests": stash_extract_norm.to_dict(orient="records"),
    }

    with open(config_file, "w") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    print(
        f"Writing STASH extraction config for package {package_name} to file: {config_file}"
    )
    extract_configs.append((package_name, config_file))

    print(" ")
    print("-" * 50)
    print(" ")

if not extract_configs:
    print("No extraction configs were generated. Exiting...")
    sys.exit(1)

sbatch_files = []
for package_name, config_file in extract_configs:
    jobtime = umstash.extract_climate_job_time(package_name)
    sbatch_file = os.path.join(
        SBATCH_DIR, f"{suite}_{package_name}_{first_yr}_{last_yr}.sbatch"
    )
    logfile = os.path.join(LOG_DIR, f"{suite}_{package_name}_{first_yr}-{last_yr}.out")

    print(f"Writing sbatch script for package {package_name} to file: {sbatch_file}")
    umstash.write_sbatch_extract(sbatch_file, config_file, jobtime, logfile)
    sbatch_files.append(sbatch_file)

print(" ")
print("-" * 50)
print(" ")
print("Preparation complete")

for sbatch_file in sbatch_files:
    print(f"Submitting job {sbatch_file}")
    result = subprocess.run(["sbatch", sbatch_file], check=True, capture_output=True, text=True)
    print(result.stdout.strip())
    print(" ")
