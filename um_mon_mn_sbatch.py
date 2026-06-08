import os
import socket
import sys
import time

import xarray as xr

import src.um_stash_extract_funcs as umstash

ROOT_DIR = os.path.dirname(__file__)
WORKSPACE_DIR = os.path.dirname(ROOT_DIR)

workspace_src = os.path.join(WORKSPACE_DIR, "src")
if workspace_src not in sys.path:
    sys.path.insert(0, workspace_src)

import um_utils as um  # type: ignore


config_file = sys.argv[1]
cfg = umstash.read_monthly_config(config_file)

suite = cfg["suite"]
start_yr = cfg["start_year"]
end_yr = cfg["end_year"]
files_to_process = cfg["files_to_process"]
mon_mn_file = cfg["output_file"]
no_yrs = int(end_yr) - int(start_yr)

os.makedirs(os.path.dirname(mon_mn_file), exist_ok=True)

print("Monthly meaning program configuration:", flush=True)
print(f"Suite: {suite}", flush=True)
print(f"Start Year: {start_yr}", flush=True)
print(f"End Year: {end_yr}", flush=True)
print(" ", flush=True)

mon_mn_xds = None
if os.path.exists(mon_mn_file):
    print(f"Loading monthly means file for {suite} and dates {start_yr}-{end_yr}", flush=True)
    mon_mn_xds = xr.open_dataset(mon_mn_file, decode_times=False)
    print(" ", flush=True)

print("The following files will be processed:", flush=True)
print(" ", flush=True)
for file in files_to_process:
    print(file, flush=True)

print(" ", flush=True)
print("-" * 50, flush=True)
print(" ", flush=True)

start_time = time.time()
var_da_list = []

for file_to_mean in files_to_process:
    file_time = time.time()
    varname = umstash.variable_name_from_processed_file(file_to_mean)

    print(f"Meaning file {file_to_mean}", flush=True)
    print(" ", flush=True)
    print(f"Variable: {varname}", flush=True)

    _, coords, xda = um.importUMData(file_to_mean)  # type: ignore
    if not isinstance(xda, xr.DataArray):
        raise TypeError(
            f"{file_to_mean} did not return a DataArray, got type {type(xda)} instead"
        )

    print(f"Original Shape: {xda.shape}", flush=True)

    var_mean, no_samp_per_yr = umstash.monthly_mean_from_dataarray(xda, no_yrs)

    varname, metadata = umstash.monthly_metadata(varname)

    if "tiles" in metadata:
        var_mean = var_mean[:, : metadata["tiles"], :, :]

    print(f"New Shape: {var_mean.shape}", flush=True)

    if "convert" in metadata:
        var_mean, metadata["attrs"]["units"] = umstash.clim_convert(
            var_mean,
            metadata["convert"],
            metadata["attrs"]["units"],
        )
        print("Conversion applied: " + metadata["convert"], flush=True)

    print("Setting metadata and coordinates...", flush=True)

    dims = list(metadata["dims"])
    attrs = metadata["attrs"]

    max_atm_lev = xda.shape[1] if len(xda.shape) > 1 else 1
    coords_dict = umstash.get_coords_dict(dims, coords, no_samp_per_yr, max_atm_lev)

    if mon_mn_xds is not None:
        coords_dict, dims = umstash.resolve_coord_conflicts(mon_mn_xds, coords_dict, dims)

    var_da = xr.DataArray(var_mean, coords=coords_dict, dims=dims, name=varname)
    for coord in list(var_da.coords):
        var_da[coord].attrs = umstash.coord_attrs(coord, str(start_yr))
    var_da.attrs = attrs

    var_da_list.append(var_da)

    print("Done!", flush=True)
    print(" ", flush=True)
    print(f"Time elapsed: {(time.time() - file_time):.2f} s", flush=True)
    print(" ", flush=True)
    print("-" * 50, flush=True)
    print(" ", flush=True)

print("All files processed", flush=True)
print("Merging dataarrays...", flush=True)

merge_time = time.time()
xds_new = xr.merge(var_da_list)

xds_new.attrs = {
    "name": "Monthly Mean Unified Model Output",
    "version": "UM 13.2",
    "suite": suite,
    "start": f"{start_yr}/01",
    "end": f"{int(end_yr)-1}/12",
}

if mon_mn_xds is not None:
    print(f"Monthly means file exists => Appending arrays to file {mon_mn_file}", flush=True)
    xds_new = xr.merge([mon_mn_xds, xds_new])
else:
    print(f"Monthly means file does not exist => Writing arrays to file {mon_mn_file}", flush=True)

encoding = {name: {"zlib": True, "complevel": 5} for name in list(xds_new.data_vars)}
umstash.write_atomic_dataset(xds_new, mon_mn_file, encoding=encoding)

print("Done!", flush=True)
print(" ", flush=True)
print(f"Time Elapsed: {time.time() - merge_time:.2f} s", flush=True)
print(" ", flush=True)
print("-" * 50, flush=True)
print(" ", flush=True)

print(f"Total Time elapsed: {(time.time() - start_time):.2f} s", flush=True)
print(f"Node: {socket.gethostname()}", flush=True)

if mon_mn_xds is not None:
    mon_mn_xds.close()
