# Prepare STASH extraction jobs for one or more suites: collect user inputs, build a YAML
# config and sbatch script per suite, and submit each job to the scheduler.
# Suites sharing a STASH version share one STASH selection; requested STASH missing from
# a version's table are dropped for those suites only.

import os
import pandas as pd
import yaml

import src.um_stash_extract_funcs as umstash

ROOT_DIR = os.path.dirname(__file__)
RUN_DIR = os.path.join(ROOT_DIR, "run")

for path in [
    RUN_DIR,
    os.path.join(RUN_DIR, "stash_extract"),
    os.path.join(RUN_DIR, "sbatch_scripts"),
    os.path.join(RUN_DIR, "logs"),
]:
    os.makedirs(path, exist_ok=True)


def _rule():
    print(" ")
    print("-----------------------------------")
    print(" ")


# --- User inputs and suite discovery ---
def prompt_suites():
    # User enters a space-separated list of one or more suites
    suites = input("Enter suite(s): ").split()
    if not suites:
        print("No suite entered. Try again...")
        exit()

    # Check to see if entered suites are available options
    all_suites = umstash.available_suites()
    missing = [suite for suite in suites if suite not in all_suites]
    if missing:
        print("Sorry, these suites are not available: " + " ".join(missing) + ". Try again...")
        exit()

    return suites


def prompt_years(suite):
    # User enters start and end year (not inclusive) of extraction for a suite
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

    _rule()

    return {
        "suite": suite,
        "first_yr": first_yr,
        "last_yr": last_yr,
        "stash_vn": umstash.suite_stash_vn(suite, first_yr, last_yr),
    }


# --- STASH selection ---
def package_selection(package_name, run, stash_lookup, label):
    # Records of a pre-defined package found in the STASH table; missing records are dropped
    stash_package = umstash.um_stash_package(
        package_name, run["suite"], run["first_yr"], run["last_yr"]
    )
    if not stash_package:
        print("That package is unavaialble for suite(s) " + label)
        exit()

    # Empty dataframe with same columns as stash_lookup to store records of all requested STASH
    stash_extract = stash_lookup.iloc[:0, :].copy()
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
        if len(code_entry) == 0:
            print(f"STASH {nsec}{nitem} ({file_fid}, {domain}) not in table for: {label} - dropped")

        stash_extract = pd.concat([stash_extract, code_entry])

    return stash_extract


def manual_selection(stash_req, stash_lookup, label):
    # Records of user-entered 5-digit STASH codes found in the STASH table; invalid codes are dropped
    stash_extract = stash_lookup.iloc[:0, :].copy()
    for code in stash_req:
        nsec = code[:2]
        nitem = code[2:]
        code_entries = stash_lookup[
            (stash_lookup["SECTION"] == nsec) & (stash_lookup["ITEM"] == nitem)
        ]
        if len(code_entries) == 0:
            _rule()
            print("STASH Request " + code + " is not valid for: " + label + " - dropped")
            print(" ")

        elif len(code_entries) > 1:
            _rule()
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

    return stash_extract


def select_stash(runs):
    # One STASH selection per STASH version; returns package name and {stash_vn: stash_extract}
    groups = {}
    for run in runs:
        groups.setdefault(run["stash_vn"], []).append(run)

    # User asked if they want to extract a pre-defined package of STASH requests
    package_name = None
    stash_req = None
    package_flag = False
    while not package_flag:
        package_extract = input("Do you want to extract a pre-defined package[y/n]? ")
        match package_extract:

            # Extract a pre-defined package
            case "y":
                package_flag = True
                package_name = input("Enter the name of the package here: ")

            # User defines package to extract as a space-separated list of 5-digit STASH codes
            case "n":
                package_flag = True
                stash_input = input("Enter a list of 5-digit STASH codes to extract: ")
                stash_req = stash_input.split()

            # User enters an option that is not 'y' or 'n'
            case _:
                print("Sorry, that is not a valid option")

    stash_by_vn = {}
    for stash_vn, group in groups.items():
        label = ", ".join(run["suite"] for run in group)
        if len(groups) > 1:
            _rule()
            print(f"STASH selection for v{stash_vn} suites: {label}")

        # STASH table is identical for all suites in a group
        first = group[0]
        stash_lookup = umstash.read_stash_table(first["suite"], first["first_yr"], first["last_yr"])

        if stash_req is None:
            stash_extract = package_selection(package_name, first, stash_lookup, label)
        else:
            stash_extract = manual_selection(stash_req, stash_lookup, label)

        _rule()

        if len(stash_extract) == 0:
            print(f"No requested STASH available for: {label} - these suites will be skipped")
        else:
            stash_extract, lev_subset = umstash.multi_levels(stash_extract, stash_req=stash_req)

            _rule()

            # A printout of all requested STASH items
            print("The following STASH requests will be extracted:")
            print(" ")
            print(stash_extract.reset_index(drop=True))

        _rule()
        stash_by_vn[stash_vn] = stash_extract

    if all(len(stash_extract) == 0 for stash_extract in stash_by_vn.values()):
        print("No requested STASH available for any suite. Exiting...")
        exit()

    if stash_req is not None:
        print("Required package names: Hourly Data => *-hourly, Daily Data => *-daily, SW Band Data => *-swband")
        package_name = input("Please enter a name for this package: ")
        print(" ")

    return package_name, stash_by_vn


# --- Config and sbatch generation ---
def submit_run(run, stash_extract, package_name, jobtime):
    suite, first_yr, last_yr = run["suite"], run["first_yr"], run["last_yr"]

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

    # The executable sbatch file is written to run/sbatch_scripts by calling write_sbatch_extract()
    # Max job runtime and logfile are also set here
    sbatch_file = os.path.join(
        RUN_DIR, "sbatch_scripts", f"{suite}_{package_name}_{first_yr}_{last_yr}.sbatch"
    )
    logfile = os.path.join(
        RUN_DIR, "logs", f"{suite}_{package_name}_{first_yr}-{last_yr}.out"
    )
    print("Writing run file " + sbatch_file)
    umstash.write_sbatch_extract(sbatch_file, stash_extract_file, jobtime, logfile)

    print("Submitting batch job...")
    sbatch_cmd = "sbatch " + sbatch_file
    os.system(sbatch_cmd)
    print(" ")


def run_summary(run, stash_extract):
    # Summary of one job: suite, period and each STASH record to be extracted
    header = f"{run['suite']} {run['first_yr']}-{run['last_yr']}"
    if len(stash_extract) == 0:
        return header + ": skipped (no requested STASH available)"

    lines = [f"{header}: {len(stash_extract)} STASH"]
    for _, stash in stash_extract.iterrows():
        lines.append(
            f"{stash['SECTION']}{stash['ITEM']} {stash['STASH_NAME']} ({stash['OUTPUT_FILE']}, {stash['TIME']})"
        )
    return "\n".join(lines)


def main():
    suites = prompt_suites()
    runs = [prompt_years(suite) for suite in suites]
    package_name, stash_by_vn = select_stash(runs)

    jobtime = input("How long should the job take (HH:MM:SS)? ")
    print(" ")

    # Now that all preparation is complete, one sbatch file per suite is submitted to JASMIN nodes
    print("Preparation complete")
    print(" ")
    for run in runs:
        stash_extract = stash_by_vn[run["stash_vn"]]
        if len(stash_extract) != 0:
            submit_run(run, stash_extract, package_name, jobtime)

    _rule()
    print("Job summary:")
    print(" ")
    for run in runs:
        print(run_summary(run, stash_by_vn[run["stash_vn"]]))
        print(" ")


if __name__ == "__main__":
    main()
