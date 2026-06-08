# Prepare a STASH extraction job: collect user inputs, build a YAML config,
# generate an sbatch script, and submit the job to the scheduler.

import os
import pandas as pd
import yaml

from src import um_stash_extract_funcs as umstash

ROOT_DIR = os.path.dirname(__file__)
RUN_DIR = os.path.join(ROOT_DIR, "run")

for path in [
    RUN_DIR,
    os.path.join(RUN_DIR, "stash_extract"),
    os.path.join(RUN_DIR, "sbatch_scripts"),
    os.path.join(RUN_DIR, "logs"),
]:
    os.makedirs(path, exist_ok=True)

# --- User inputs and suite discovery ---
# User enters a suite
suite = input("Enter suite: ")

# List of all suites in the workspace
all_suites = umstash.available_suites()

# Check to see if entered suite is an available option
if suite not in all_suites:
    print("Sorry, that suite is not available. Try again...")
    exit()

# User enters start and end year (not inclusive) of extraction
suite_min_yr, suite_max_yr = umstash.suite_available_years(suite)

print(f"Years available for suite {suite}: {suite_min_yr} - {suite_max_yr}")
first_yr_input = input("Please enter the start year: ")
last_yr_input = input("Please enter the last year: ")

try:
    first_yr, last_yr = umstash.validate_whole_year_block(
        first_yr_input,
        last_yr_input,
        min_yr=suite_min_yr,
        max_yr=suite_max_yr,
    )
except ValueError as exc:
    print(f"Invalid year range: {exc}")
    exit()

print(" ")
print("-----------------------------------")
print(" ")

# --- STASH selection ---
# Read in STASH table for suite
stash_lookup = umstash.read_stash_table(suite, first_yr, last_yr)

# Create empty dataframe with same columns as stash_lookup to store records of all STASH requested by user for extraction
stash_extract = stash_lookup.iloc[:0, :].copy()

# User asked if they want to extract a pre-defined package of STASH requests
package_flag = False
while not package_flag:
    package_extract = input("Do you want to extract a pre-defined package[y/n]? ")
    match package_extract:

        # Extract a pre-defined package 
        case "y":
            package_flag = True
            package_name = input("Enter the name of the package here: ")
            stash_package = umstash.um_stash_package(package_name, suite, first_yr, last_yr)
            if not stash_package:
                print("That package is unavaialble for suite " + suite)
                exit()

            else:
                for stash in stash_package:
                    nsec = stash["SECTION"]
                    nitem = stash["ITEM"]
                    file_fid = stash["OUTPUT_FILE"]
                    domain = stash["DOMAIN"]
                    code_entry = stash_lookup[
                        (stash_lookup["SECTION"] == nsec)
                        & (stash_lookup["ITEM"] == nitem)
                        & (stash_lookup["OUTPUT_FILE"] == file_fid)
                        & (stash_lookup["DOMAIN"] == domain)
                    ]

                    stash_extract = pd.concat([stash_extract, code_entry])
                
                print(" ")
                print("-----------------------------------")
                print(" ")

                stash_extract, lev_subset = umstash.multi_levels(stash_extract)

                print(" ")
                print("-----------------------------------")
                print(" ")

                print("The following STASH requests will be extracted:")
                print(" ")
                print(stash_extract.reset_index(drop=True))
                print(" ")
                print("-----------------------------------")
                print(" ")

        # User defines package to extract
        case "n":
            package_flag = True
            # User enters a space-separated list of 5-digit STASH codes
            stash_input = input("Enter a list of 5-digit STASH codes to extract: ")
            stash_req = stash_input.split()

            # List of stash_codes from suite stash table
            stash_code = list((stash_lookup["SECTION"] + stash_lookup["ITEM"]).values)


            for code in stash_req:
                nsec = code[:2]
                nitem = code[2:]
                code_entries = stash_lookup[
                    (stash_lookup["SECTION"] == nsec) & (stash_lookup["ITEM"] == nitem)
                ]
                if len(code_entries) == 0:
                    print(" ")
                    print("-----------------------------------")
                    print(" ")
                    print("STASH Request " + code + " is not valid for this suite")
                    print(" ")

                elif len(code_entries) > 1:
                    print(" ")
                    print("-----------------------------------")
                    print(" ")
                    print("STASH code " + code + " has multiple records in this suite:")
                    print(" ")
                    print(code_entries)
                    print(" ")
                    idx_select = int(
                        input(
                            "Which record would you like to extract? Enter the record number (left) here: "
                        )
                    )
                    stash_extract = pd.concat(
                        [stash_extract, stash_lookup.loc[[idx_select]]]
                    )

                else:
                    stash_extract = pd.concat([stash_extract, code_entries])

            print(" ")
            print("-----------------------------------")
            print(" ")

            stash_extract, lev_subset = umstash.multi_levels(stash_extract, stash_req=stash_req)

            print(" ")
            print("-----------------------------------")
            print(" ")

            # A printout of all requested STASH items 
            print("The following STASH requests will be extracted:")
            print(" ")
            print(stash_extract.reset_index(drop=True))
            print(" ")
            print("-----------------------------------")
            print(" ")
            print("Required package names: Hourly Data => *-hourly, Daily Data => *-daily, SW Band Data => *-swband")
            package_name = input("Please enter a name for this package: ")
            print(" ")
        
        # User enters an option that is not 'y' or 'n'
        case _:
            print("Sorry, that is not a valid option")

# --- Config and sbatch generation ---
# The stash_extract dataframe is written to a .yaml file in the run/stash_extract directory.
# Each file is identified by suite and package name. If it already exists, it is replaced.
stash_extract_file = os.path.join(
    RUN_DIR, "stash_extract", f"{suite}_{package_name}_{first_yr}_{last_yr}.yaml"
)
if os.path.isfile(stash_extract_file):
    os.remove(stash_extract_file)

stash_extract_norm = stash_extract.copy()
stash_extract_norm["SECTION"] = (
    stash_extract_norm["SECTION"].astype(str).str.lstrip("0").replace("", "0")
)

stash_extract_norm["ITEM"] = (
    stash_extract_norm["ITEM"].astype(str).str.lstrip("0").replace("", "0")
)

config = {
    "suite": suite,
    "package_name": package_name,
    "start_year": int(first_yr),
    "end_year": int(last_yr),
    "stash_requests": stash_extract_norm.to_dict(orient="records"),
}

print("Writing STASH extraction list to " + stash_extract_file)
with open(stash_extract_file, "w") as handle:
    yaml.safe_dump(config, handle, sort_keys=False)

print(" ")

# The executable sbatch file is written to sbatch_job_files/sbatch_scripts by calling write_sbatch()
# Max job runtime and logfile are also set here
sbatch_file = os.path.join(
    RUN_DIR, "sbatch_scripts", f"{suite}_{package_name}_{first_yr}_{last_yr}.sbatch"
)
jobtime = input("How long should the job take (HH:MM:SS)? ")
logfile = os.path.join(
    RUN_DIR, "logs", f"{suite}_{package_name}_{first_yr}-{last_yr}.out"
)
print("Writing run file " + sbatch_file)
umstash.write_sbatch_extract(sbatch_file, stash_extract_file, jobtime, logfile)

print(" ")

# Now that all peparation is complete, the sbatch file is submitted to JASMIN nodes
print("Preparation complete")
print("Submitting batch job...")
sbatch_cmd = "sbatch " + sbatch_file
os.system(sbatch_cmd)