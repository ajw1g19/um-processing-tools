# Prepare a monthly-mean job: collect inputs, build a YAML config,
# generate an sbatch script, and submit the job.

import os
import subprocess
import sys

import xarray as xr

from src import um_stash_extract_funcs as umstash

ROOT_DIR = os.path.dirname(__file__)
RUN_DIR = os.path.join(ROOT_DIR, "run")
CONFIGS_DIR = os.path.join(RUN_DIR, "monthly_mean")
SBATCH_DIR = os.path.join(RUN_DIR, "sbatch_scripts")
LOG_DIR = os.path.join(RUN_DIR, "logs")

for path in [CONFIGS_DIR, SBATCH_DIR, LOG_DIR]:
    os.makedirs(path, exist_ok=True)

suite = input("Enter suite: ").strip()
all_suites = umstash.available_suites()
if suite not in all_suites:
    print("Sorry, that suite is not available. Try again...")
    sys.exit(1)

suite_min_yr, suite_max_yr = umstash.suite_available_years(suite)
print(f"Years available for suite {suite}: {suite_min_yr} - {suite_max_yr}")
start_yr_input = input("Enter the start year: ").strip()
end_yr_input = input("Enter the last year (exclusive): ").strip()

try:
    start_yr, end_yr = umstash.validate_whole_year_block(
        start_yr_input,
        end_yr_input,
        min_yr=suite_min_yr,
        max_yr=suite_max_yr,
    )
except ValueError as exc:
    print(f"Invalid year range: {exc}")
    sys.exit(1)

avail_files = umstash.available_processed_files(suite, start_yr, end_yr)
mon_mn_file = umstash.monthly_output_file(suite, start_yr, end_yr)

existing_vars = []
if os.path.isfile(mon_mn_file):
    print(" ")
    print(f"Monthly means file exists for {suite} and dates {start_yr}-{end_yr}")
    print("Loading variables...")

    with xr.open_dataset(mon_mn_file, decode_times=False) as ds:
        existing_vars = list(ds.data_vars)

    print("The following variables are present in the monthly means file:")
    print(" ")
    for var in existing_vars:
        print(var)
    print(" ")

    del_flag = input("Do you want to overwrite any variables in this list [y/n]? ").strip()
    if del_flag == "y":
        del_vars = input("Enter the variables here [space-separated]: ").split()
        print("Deleting variables...")
        with xr.open_dataset(mon_mn_file, decode_times=False) as ds:
            ds_new = ds.drop_vars(del_vars, errors="ignore").load()
        umstash.write_atomic_dataset(ds_new, mon_mn_file)

        existing_vars = [var for var in existing_vars if var not in del_vars]

    print(" ")

if not avail_files:
    print(f"No compatible files for suite {suite} and dates {start_yr}-{end_yr}")
    print("Exiting...")
    sys.exit(1)

files_to_mean = [
    f for f in avail_files if umstash.variable_name_from_processed_file(f) not in existing_vars
]

if not files_to_mean:
    print(f"No compatible files for suite {suite} and dates {start_yr}-{end_yr}")
    print("Exiting...")
    sys.exit(0)

print("The following files are available to process:")
print(" ")
for file in files_to_mean:
    print(file)

print(" ")
print("-" * 30)
print(" ")

config_file = os.path.join(CONFIGS_DIR, f"{suite}_mon_mn_{start_yr}-{end_yr}.yaml")
umstash.write_monthly_config(
    config_path=config_file,
    suite=suite,
    start_yr=start_yr,
    end_yr=end_yr,
    files_to_process=files_to_mean,
    output_file=mon_mn_file,
)

print(f"Job configuration written to {config_file}")
print(" ")

sbatch_file = os.path.join(SBATCH_DIR, f"{suite}_mon_mn_{start_yr}-{end_yr}.sbatch")
jobtime = input("How long should the job take (HH:MM:SS)? ").strip()
logfile = os.path.join(LOG_DIR, f"{suite}_mon_mn_{start_yr}-{end_yr}.out")
print("Writing run file " + sbatch_file)
umstash.write_sbatch_monthly(sbatch_file, config_file, jobtime, logfile)

print(" ")
print("Preparation complete")
print("Submitting batch job...")

result = subprocess.run(["sbatch", sbatch_file], check=True, capture_output=True, text=True)
print(result.stdout.strip())
