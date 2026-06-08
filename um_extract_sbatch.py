import concurrent.futures
import glob
import os
import re
import socket
import sys
import time

import cf
import numpy as np
import pandas as pd
import xarray as xr
import yaml

from src import um_stash_extract_funcs as umstash
from src.um_metadata import get_metadata

ROOT_DIR = os.path.dirname(__file__)
WORKSPACE_DIR = umstash.workspace_dir()
CONFIG_DIR = os.path.join(ROOT_DIR, "config")

# --- Logging and formatting ---
# Necessary to get stash_extract dataframe to print properly in log-file
pd.set_option("display.max_columns", None)
pd.set_option("display.expand_frame_repr", False)


# --- Log header helpers ---
def print_job_header(suite, first_yr, last_yr, package_name, output_dir, stash_count):
    # Format and print top-of-log summary; used only in this worker script.
    title = "STASH EXTRACTION JOB"
    lines = [
        f"Suite       : {suite}",
        f"Years       : {first_yr} to {last_yr}",
        f"Package     : {package_name}",
        f"Requests    : {stash_count}",
        f"Output dir  : {output_dir}",
    ]
    width = max(len(title), max(len(line) for line in lines)) + 4

    print("=" * width, flush=True)
    print(f"{title:^{width}}", flush=True)
    print("-" * width, flush=True)
    for line in lines:
        print(f"  {line}", flush=True)
    print("=" * width, flush=True)
    return width


def print_section_title(title, width):
    # Print section separators in logs; used only in this worker script.
    print(" ", flush=True)
    print(f"{title:^{width}}", flush=True)
    print("-" * width, flush=True)
    print(" ", flush=True)

# --- File discovery ---
# Generate files to read via cf.read()
def generate_files(suite, year, fids):
    # Build expected PP file paths for a suite/year; used by extract_year.
    file_list = []
    base_dir = os.path.join(WORKSPACE_DIR, "Model_Output", suite)

    for fid in fids:
        file_list.extend(
            [
                os.path.join(
                    base_dir,
                    f"{year}0101T0000Z",
                    f"{suite[-5:]}a.{fid}{year}{month:02d}01.pp",
                )
                for month in np.arange(1, 4)
            ]
        )
        file_list.extend(
            [
                os.path.join(
                    base_dir,
                    f"{year}0401T0000Z",
                    f"{suite[-5:]}a.{fid}{year}{month:02d}01.pp",
                )
                for month in np.arange(4, 7)
            ]
        )
        file_list.extend(
            [
                os.path.join(
                    base_dir,
                    f"{year}0701T0000Z",
                    f"{suite[-5:]}a.{fid}{year}{month:02d}01.pp",
                )
                for month in np.arange(7, 10)
            ]
        )
        file_list.extend(
            [
                os.path.join(
                    base_dir,
                    f"{year}1001T0000Z",
                    f"{suite[-5:]}a.{fid}{year}{month:02d}01.pp",
                )
                for month in np.arange(10, 13)
            ]
        )
    return file_list

# --- Output naming ---
def file_suffix(package_name, code):
    # Build intermediate filename suffix from package type; used by extract_year and merge loop.
    suffix_map = {"hourly": "hourly", "daily": "daily", "swband": "swband"}
    matches = [suffix for key, suffix in suffix_map.items() if key in package_name]

    if len(matches) > 1:
        raise ValueError(f"Multiple time profiles detected in package '{package_name}'")
    if len(matches) == 1:
        return f"{code}-{matches[0]}"

    return f"{code}"


# --- Year-level extraction ---
# Extraction function for reading files and pulling out individual records, slicing levels if necessary
def extract_year(year):
    # Extract one year of requested fields and write intermediate NetCDF files.
    pp_files = [f for f in generate_files(suite, year, file_ids) if os.path.exists(f)]
    if not pp_files:
        return None, f"No files found for year {year}"

    um_fields = cf.read(pp_files)

    ncfiles = []
    for i, code in enumerate(stash_codes):
        matches = [field for field in um_fields if field.get_property("stash_code") == code]

        desired_shape = umstash.fieldShape(domain_profiles[i], time_profiles[i])
        levels = stash_levels[i]

        if len(matches) > 1:
            all_match = all(field.shape == desired_shape for field in matches)
            if all_match:
                selected_field = matches[0]
            else:
                for field in matches:
                    if field.shape == desired_shape:
                        selected_field = field
        elif len(matches) == 1:
            selected_field = matches[0]
        else:
            print(f"No records match for code {code}", flush=True)

        if (code == "1509") or (code == "1510"):
            selected_field = selected_field[:, levels - 1]
        elif levels > 1:
            selected_field = selected_field[:, :levels]

        nc_fname = f"{suite_dir}{year}_{file_suffix(package_name, code)}.nc"
        cf.write(selected_field, nc_fname)
        ncfiles.append(nc_fname)

    return ncfiles, f"Year complete: {year}"

# --- Job configuration ---
# Read stash extract file and the key variables
stash_extract_file = sys.argv[1]
with open(stash_extract_file, "r") as handle:
    cfg = yaml.safe_load(handle)

suite = cfg["suite"]
package_name = cfg["package_name"]
first_yr = cfg["start_year"]
last_yr = cfg["end_year"]
stash_extract = pd.DataFrame(cfg["stash_requests"])

suite_dir = os.path.join(WORKSPACE_DIR, "Model_Output", suite, "")

# Read elements of stash_extraction file
file_ids = np.unique(stash_extract["OUTPUT_FILE"])

# Format stash_codes: where section is nonzero, item code should be three digits with leading zeros
sections = stash_extract["SECTION"].astype(str)
items = stash_extract["ITEM"].astype(int).astype(str)
stash_codes = np.array([
    sec + itm.zfill(3) if sec != "0" else itm
    for sec, itm in zip(sections, items)
])
stash_levels = np.array(stash_extract["LEVELS"].astype(int))
domain_profiles = np.array(stash_extract["DOMAIN"])
time_profiles = np.array(stash_extract["TIME"])

# --- Log header and request listing ---
# Printing information to the logfile
output_dir = os.path.join(WORKSPACE_DIR, "Processed_Output", suite)
header_width = print_job_header(
    suite,
    first_yr,
    last_yr,
    package_name,
    output_dir,
    len(stash_extract),
)
print_section_title("STASH REQUESTS", header_width)
print(stash_extract, flush=True)
print(" ", flush=True)
print("-" * header_width, flush=True)
print(" ", flush=True)

if os.path.isdir(output_dir):
    print("Output directory exists", flush=True)
else:
    os.makedirs(output_dir, exist_ok=True)
    print("Created Processed_Output folder for suite", flush=True)

print(" ", flush=True)
print("-" * header_width, flush=True)
print(" ", flush=True)

start_time = time.time()

# --- Extraction loop ---
# Extraction code, running in parallel
extract_time = time.time()

years_to_process = np.arange(int(first_yr), int(last_yr))

all_files = []
with concurrent.futures.ProcessPoolExecutor() as executor:
    print("Extracting fields year-by-year...\n", flush=True)
    futures = {executor.submit(extract_year, year): year for year in years_to_process}
    for i, future in enumerate(concurrent.futures.as_completed(futures)):
        ncfiles, msg = future.result()
        if ncfiles is not None:
            all_files.extend(ncfiles)
        print(msg, f"({i+1}/{len(years_to_process)})", flush=True)

print(" ", flush=True)
print(f"Time elapsed: {(time.time() - extract_time):.2f} s", flush=True)
print(" ", flush=True)
print("-" * header_width, flush=True)
print(" ", flush=True)

for i, code in enumerate(stash_codes):
    files_to_combine = [
        f for f in all_files if f.endswith(f"{file_suffix(package_name, code)}.nc")
    ]
    var = f"UM_m01s{sections[i].zfill(2)}i{items[i].zfill(3)}_vn1302"

    print(f"Processing item {code}: {var}", flush=True)
    print(" ", flush=True)

    # Date codes for output file
    start_date = str(years_to_process[0]) + "01"
    end_date = str(years_to_process[-1]) + "12"

    combine_time = time.time()

    # Combine intermediate files and write to Processed_Output/
    print(f"Combining {len(files_to_combine)} .nc files", flush=True)

    xds = xr.open_mfdataset(
        sorted(files_to_combine),
        combine="nested",
        concat_dim="time",
        parallel=False,
    )
    xds.load()
    print(f"Files combined successfully with new shape: {xds[var].shape}", flush=True)

    print(" ", flush=True)
    print(f"Time elapsed: {(time.time() - combine_time):.2f} s", flush=True)
    print(" ", flush=True)
    
    meta_time = time.time()
    print("Removing unwanted variables and fixing metadata...", flush=True)

    vars_to_keep = [var] + list(xds[var].dims)
    vars_to_drop = [v for v in list(xds.data_vars) + list(xds.coords) if v not in vars_to_keep]
    print(f"Dropped vars: {vars_to_drop}", flush=True)
    xds_new = xds.drop_vars(vars_to_drop)

    varname, metadata = get_metadata(
        var, package_name, level=stash_levels[i], config_dir=CONFIG_DIR
    )
    print(f"New var name: {varname}", flush=True)
    xds_new[var].attrs = metadata["attrs"]
    xds_new = xds_new.rename({var:varname})

    print(" ", flush=True)

    # Checking for existing files with the same data and removing if necessary
    current_var_files = glob.glob(os.path.join(output_dir, f"{varname}_*.nc"))
    current_var_files = [
        f for f in current_var_files if re.search(rf"{varname}_[0-9].*\.nc$", f)
    ]
    for file in current_var_files:
        start_yr = re.split(r"[_\-.]", file)[-3][:4]
        end_yr = re.split(r"[_\-.]", file)[-2][:4]
        if (int(start_yr) >= years_to_process[0]) and (int(end_yr) <= years_to_process[-1]):
            os.remove(file)
            print(f"Removed unnecessary file: {file}", flush=True)
            print(" ", flush=True)

    print("Writing and compressing adjusted file...", flush=True)
    new_nc_name = os.path.join(output_dir, f"{varname}_{start_date}-{end_date}.nc")
    encoding = {varname: {"zlib": True, "complevel": 5}}
    umstash.write_atomic_dataset(xds_new, new_nc_name, encoding=encoding)
    xds.close()
    print(f"File written: {new_nc_name}", flush=True)

    print(" ", flush=True)
    print(f"Time elapsed: {(time.time() - meta_time):.2f} s", flush=True)
    print(" ", flush=True)

    # Remove all uncombined nc files
    print("Removing uncombined files...", flush=True)
    for file in files_to_combine:
        try:
            os.remove(file)
        except FileNotFoundError:
            pass
    print("Done!", flush=True)

    print(" ", flush=True)
    print("-" * header_width, flush=True)
    print(" ", flush=True)

print(f"Time elapsed: {(time.time() - start_time):.2f} s", flush=True)
print(f"Node: {socket.gethostname()}", flush=True)








