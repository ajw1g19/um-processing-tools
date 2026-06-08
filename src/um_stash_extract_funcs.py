import glob
import os
import re
import sys
import tempfile

import numpy as np
import pandas as pd
import xarray as xr
import yaml

from src.um_metadata import get_metadata

pd.options.mode.copy_on_write = True

# --- Config and package helpers ---


def _root_dir():
    # Resolve STASH_extract root directory; used by path helpers in this module.
    return os.path.dirname(os.path.dirname(__file__))


def workspace_dir():
    # Resolve workspace root; used by stash_extraction.py, um_extract_sbatch.py, stash_mon_mn.py, and extract_climate.py.
    return os.path.dirname(_root_dir())


def _config_dir():
    # Resolve STASH_extract config directory; used by YAML and template readers.
    return os.path.join(_root_dir(), "config")


def _load_yaml(filename):
    # Load a YAML file from STASH_extract/config; used by package/version helpers.
    path = os.path.join(_config_dir(), filename)
    with open(path, "r") as handle:
        return yaml.safe_load(handle) or {}


def _parse_condition(expr):
    # Parse conditional expressions from config/packages.yaml rules.
    match = re.match(r"^stash_vn\s*(==|>=|<=|>|<)\s*([0-9.]+)$", expr.strip())
    if not match:
        raise ValueError(f"Invalid condition expression '{expr}'")
    op, value = match.group(1), float(match.group(2))
    return op, value


def _condition_met(stash_vn, expr):
    # Evaluate a stash_vn rule condition; used by um_stash_package.
    op, value = _parse_condition(expr)
    if op == ">":
        return stash_vn > value
    if op == ">=":
        return stash_vn >= value
    if op == "<":
        return stash_vn < value
    if op == "<=":
        return stash_vn <= value
    if op == "==":
        return stash_vn == value
    raise ValueError(f"Unsupported operator '{op}' in condition '{expr}'")


def fieldShape(domain, time):
    # Return expected field shape for STASH domain/time profiles; used by um_extract_sbatch.py.
    # N.B. This function can't handle DPBLTH domains as they have two different
    # output shapes in the STASH
    domain_shapes = {
        "DIAG": (144, 192),
        "DALLTH": (85, 144, 192),
        "D52TH": (52, 144, 192),
        "DALLRHSW": (86, 6, 144, 192),
        "DP28": (28, 145, 192),
        "DALLRH": (85, 144, 192),
        "DTILE": (27, 144, 192),
        "D1TH": (144, 192),
        "DPFTS": (13, 144, 192),
        "DSOIL": (4, 144, 192),
        "DIAGAOT": (6, 144, 192),
        "DALLTHAOT": (85, 6, 144, 192),
        "DP17": (17, 145, 192),
        "DP36CCMZ": (36, 145, 1),
    }
    time_shapes = {
        "T6HMONM": 12,
        "TMONMN": 12,
        "TMONMNH-8": 96,
        "TMONMNH-24": 288,
        "TDAYM": 360,
        "TDAYMN": 360,
        "TDAYMIN": 360,
        "TDAYMAX": 360,
    }

    if domain not in domain_shapes:
        supported = ", ".join(sorted(domain_shapes.keys()))
        raise ValueError(f"Unsupported domain '{domain}'. Supported: {supported}")
    if time not in time_shapes:
        supported = ", ".join(sorted(time_shapes.keys()))
        raise ValueError(f"Unsupported time profile '{time}'. Supported: {supported}")

    return (time_shapes[time], *domain_shapes[domain])


def resolve_stash_vn(entry, startyr, endyr=None):
    # Resolve suite STASH version for a requested period; used by read_stash_table and um_stash_package.
    if isinstance(entry, (int, float)):
        return entry

    if startyr is None:
        sys.exit("startyr must be provided when stash verisions vary by year")

    if endyr is None:
        endyr = startyr

    try:
        keys = sorted(int(k) for k in entry.keys())
    except Exception:
        sys.exit("Invalid stash-vn dictionary keys; expected year-like keys")

    intervals = []
    for i, k in enumerate(keys):
        start = k
        if i + 1 < len(keys):
            end = keys[i + 1] - 1
        else:
            end = float("inf")
        intervals.append((start, end, entry[str(k)] if str(k) in entry else entry[k]))

    start_interval = next(
        (iv for iv in intervals if iv[0] <= int(startyr) <= iv[1]), None
    )
    end_interval = next(
        (iv for iv in intervals if iv[0] <= int(endyr) - 1 <= iv[1]), None
    )

    if start_interval is None or end_interval is None or start_interval[0] != end_interval[0]:
        msg = (
            f"Requested years [{startyr},{endyr}] span multiple STASH-version intervals. "
            "Please request a period contained entirely within a single STASH version."
        )
        sys.exit(msg)

    return start_interval[2]


def read_stash_table(suite, startyr=None, endyr=None):
    # Load suite-specific STASH lookup table from config/stash.xlsx; used by stash_extraction.py and extract_climate.py.
    suite_stash_vn = _load_yaml("um_stash_vn.yaml")

    if suite not in suite_stash_vn:
        sys.exit(f"Suite '{suite}' not found in sbatch_job_files/um_stash_vn.yaml")

    stash_vn = resolve_stash_vn(suite_stash_vn[suite], startyr, endyr)
    
    stash_extract = pd.read_excel(
        os.path.join(_config_dir(), "stash.xlsx"),
        sheet_name=f"stash_v{stash_vn}",
        dtype={"SECTION": str, "ITEM": str},
    )

    return stash_extract


def um_stash_package(name, suite, startyr=None, endyr=None):
    # Resolve a package from config/packages.yaml, applying stash-version append/rule logic.
    suite_stash_vn = _load_yaml("um_stash_vn.yaml")
    if suite not in suite_stash_vn:
        sys.exit(f"Suite '{suite}' not found in config/um_stash_vn.yaml")

    stash_vn = resolve_stash_vn(suite_stash_vn[suite], startyr, endyr)
    packages = _load_yaml("packages.yaml").get("packages", {})

    if name not in packages:
        print(f"{name} is not a valid package, please try again")
        return []

    package = packages[name]
    items = list(package.get("items", []))

    for addition in package.get("append", []):
        if _condition_met(stash_vn, addition["when"]):
            items.extend(addition.get("items", []))

    for rule in package.get("rules", []):
        if not _condition_met(stash_vn, rule["when"]):
            continue
        set_values = rule.get("set", {})
        if rule.get("apply_to") == "all":
            for item in items:
                item.update(set_values)
        elif "apply_to_indices" in rule:
            for idx in rule["apply_to_indices"]:
                if idx < 0 or idx >= len(items):
                    raise IndexError(f"Rule index {idx} out of range for package '{name}'")
                items[idx].update(set_values)
        else:
            raise ValueError(f"Invalid rule in package '{name}': {rule}")

    return items

def multi_levels(stash_extract, stash_req=None):
    # Interactive level selector for multi-level requests; used by stash_extraction.py.

    multi_levels = stash_extract[stash_extract["LEVELS"] > 1.0]
    if len(multi_levels) != 0:
        print("The following requests have multiple levels:")
        print(" ")
        print(multi_levels.reset_index(drop=True))
        print(" ")
        lev_flag = False
        while not lev_flag:
            lev_subset = input("Do you want to extract a subset of these levels[y/n]? ")
            match lev_subset:
                case "y":
                    if stash_req:
                        if "01509" in stash_req or "01510" in stash_req:
                            print("N.B. for STASH codes 01509 and 01510, only the selected level will be extracted")
                            diag_levs = input("Please enter the level number, per diagnostic, that you want to extract: ")
                        else:
                            diag_levs = input("Please enter the number of levels, per diagnostic, that you want to extract (from surface): ")
                    else:
                        diag_levs = input("Please enter the number of levels, per diagnostic, that you want to extract (from surface): ")
                    
                    if isinstance(diag_levs, str):
                        diag_levs = [int(k) for k in diag_levs.split()]
                        
                    if len(diag_levs) == 1:
                        stash_extract.loc[
                            stash_extract.INDEX.isin(multi_levels.INDEX), ["LEVELS"]
                        ] = diag_levs
                    else:
                        multi_levels["NLEVELS"] = diag_levs
                        stash_extract.loc[
                            stash_extract.INDEX.isin(multi_levels.INDEX), ["LEVELS"]
                        ] = multi_levels["NLEVELS"]

                    lev_flag = True

                case "n":
                    print("Understood, continuing with extraction...")
                    lev_flag = True
                case _:
                    print("Sorry, that is not a valid option")

        return stash_extract, lev_subset

    # No multi-level variables => No need to adjust stash_extract
    else:
        print("No multi-level records to process")
        lev_subset = "n"
        return stash_extract, lev_subset



def write_sbatch_extract(
    fname,
    extract_file,
    jobtime,
    logfile,
    mem_per_cpu="5G",
    template_path=None,
    module_load="jaspy",
    account="mh_gsp",
    partition="standard",
    qos="high",
    nodes=1,
    ntasks=10,
    python="python",
    work_dir=None,
    worker_path=None,
):
    # Render sbatch script from config/sbatch_template.sh; used by extraction, monthly, and extract_climate drivers.

    if template_path is None:
        template_path = os.path.join(_config_dir(), "sbatch_template.sh")
    if work_dir is None:
        work_dir = _root_dir()
    if worker_path is None:
        worker_path = os.path.join(_root_dir(), "um_extract_sbatch.py")

    with open(template_path, "r") as handle:
        template = handle.read()

    values = {
        "account": account,
        "partition": partition,
        "qos": qos,
        "nodes": nodes,
        "ntasks": ntasks,
        "time": jobtime,
        "output": logfile,
        "mem_per_cpu": mem_per_cpu,
        "module_load": module_load,
        "python": python,
        "config_path": extract_file,
        "work_dir": work_dir,
        "worker_path": worker_path,
    }

    content = template.format_map(values)
    with open(fname, "w") as sbatch_file:
        sbatch_file.write(content)


def extract_climate_packages():
    # Predefined package order used by extract_climate.py.
    return [
        "spinup",
        "surfacefrac",
        "soil-moisture",
        "soil-cn",
        "veg",
        "productivity",
        "surfrad",
        "precip",
        "wind",
        "pressure",
    ]


def extract_climate_job_time(package_name):
    # Default per-package walltime used by extract_climate.py.
    jobtimes = {
        "spinup": "00:20:00",
        "surfacefrac": "01:00:00",
        "soil-moisture": "01:00:00",
        "soil-cn": "01:00:00",
        "veg": "01:00:00",
        "productivity": "01:30:00",
        "surfrad": "01:30:00",
        "precip": "01:00:00",
        "wind": "01:30:00",
        "pressure": "00:45:00",
    }
    if package_name not in jobtimes:
        return "01:00:00"
    return jobtimes[package_name]


# --- Monthly-mean helpers ---


def monthly_output_file(suite, start_yr, end_yr):
    # Build consolidated monthly output filename; used by stash_mon_mn.py.
    # end_yr is exclusive and the output period is YYYY01-(end_yr-1)12
    return os.path.join(
        workspace_dir(),
        "Monthly_Means_Files",
        f"{suite}_monthly_means_{int(start_yr)}01-{int(end_yr)-1}12.nc",
    )


def available_suites():
    # List available suites from workspace Model_Output; used by stash_extraction.py, stash_mon_mn.py, and extract_climate.py.
    pattern = os.path.join(workspace_dir(), "Model_Output", "u-*")
    return [os.path.basename(path) for path in sorted(glob.glob(pattern))]


def suite_available_years(suite):
    # Return inclusive/exclusive suite year bounds from cycle folders; used by stash_extraction.py, stash_mon_mn.py, and extract_climate.py.
    cycle_dirs = glob.glob(
        os.path.join(workspace_dir(), "Model_Output", suite, "*T0000Z")
    )
    years = sorted({int(os.path.basename(path)[:4]) for path in cycle_dirs})
    if not years:
        raise ValueError(f"No cycle directories found for suite '{suite}'")
    return min(years), max(years) + 1


def validate_whole_year_block(start_yr, end_yr, min_yr=None, max_yr=None):
    # Validate start/end year input as an exclusive-end whole-year window; used by stash_extraction.py, stash_mon_mn.py, and extract_climate.py.
    try:
        start = int(start_yr)
        end = int(end_yr)
    except ValueError as exc:
        raise ValueError("Start and end year must be integers") from exc

    if end <= start:
        raise ValueError("End year must be greater than start year")
    if min_yr is not None and start < int(min_yr):
        raise ValueError(f"Start year {start} is below available minimum {min_yr}")
    if max_yr is not None and end > int(max_yr):
        raise ValueError(f"End year {end} is above available maximum {max_yr}")

    return start, end


def available_processed_files(suite, start_yr, end_yr):
    # List processed NetCDF files for a suite/time window; used by stash_mon_mn.py.
    pattern = os.path.join(
        workspace_dir(),
        "Processed_Output",
        suite,
        f"*_{int(start_yr)}01-{int(end_yr)-1}12.nc",
    )
    files = sorted(glob.glob(pattern))
    return [f for f in files if not os.path.basename(f).startswith(f"{suite}_")]


def variable_name_from_processed_file(path):
    # Parse variable token from processed filename; used by stash_mon_mn.py and um_mon_mn_sbatch.py.
    return os.path.basename(path).rsplit("_", 1)[0]


def write_atomic_dataset(dataset, destination, mode="w", format="NETCDF4", encoding=None):
    # Write dataset via temp-file replace for safer updates; used by um_extract_sbatch.py, stash_mon_mn.py, and um_mon_mn_sbatch.py.
    output_dir = os.path.dirname(destination)
    os.makedirs(output_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=os.path.basename(destination) + ".",
        suffix=".tmp",
        dir=output_dir,
        delete=False,
    ) as handle:
        tmp_path = handle.name

    try:
        dataset.to_netcdf(tmp_path, mode=mode, format=format, encoding=encoding)
        os.replace(tmp_path, destination)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def write_monthly_config(config_path, suite, start_yr, end_yr, files_to_process, output_file):
    # Write monthly worker YAML config; used by stash_mon_mn.py.
    config = {
        "suite": suite,
        "start_year": int(start_yr),
        "end_year": int(end_yr),
        "files_to_process": list(files_to_process),
        "output_file": output_file,
    }
    with open(config_path, "w") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)


def read_monthly_config(config_path):
    # Read/validate monthly worker YAML config; used by um_mon_mn_sbatch.py.
    with open(config_path, "r") as handle:
        cfg = yaml.safe_load(handle) or {}

    required = ["suite", "start_year", "end_year", "files_to_process", "output_file"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"Monthly config missing required keys: {', '.join(missing)}")

    cfg["start_year"] = int(cfg["start_year"])
    cfg["end_year"] = int(cfg["end_year"])
    cfg["files_to_process"] = [str(path).strip() for path in cfg["files_to_process"] if str(path).strip()]
    return cfg


def write_sbatch_monthly(
    fname,
    config_file,
    jobtime,
    logfile,
    mem_per_cpu="20G",
    ntasks=1,
    qos="standard",
):
    # Write sbatch script configured for the monthly worker; used by stash_mon_mn.py.
    worker = os.path.join(_root_dir(), "um_mon_mn_sbatch.py")
    write_sbatch_extract(
        fname=fname,
        extract_file=config_file,
        jobtime=jobtime,
        logfile=logfile,
        mem_per_cpu=mem_per_cpu,
        qos=qos,
        ntasks=ntasks,
        worker_path=worker,
    )


def clim_convert(data, method, old_units):
    # Apply simple climate unit conversions for monthly outputs; used by um_mon_mn_sbatch.py.
    if method == "temp":
        return data - 273.15, "C"
    if method == "precip":
        return data * (24 * (60**2) * 30), "mm"
    if method == "psec2pyr":
        return data * (24 * (60**2) * 360), f"{old_units[:-3]}yr-1"
    raise ValueError(f"Unsupported conversion method '{method}'")


def monthly_metadata(varname):
    # Route monthly variable metadata lookup to src/um_metadata.py; used by um_mon_mn_sbatch.py.
    if "hrly" in varname:
        return get_metadata(varname, "hourly")
    if "daily" in varname:
        return get_metadata(varname, "daily")
    if "sw_band" in varname:
        return get_metadata(varname, "swband")
    return get_metadata(varname, "default", config_dir=_config_dir())


def _atm_coords(grid):
    # Provide fixed atmosphere grid heights for monthly coordinate generation.
    if grid == "rho":
        return np.array([
            1.0000004e01, 3.6666672e01, 7.6666672e01, 1.3000002e02, 1.9666663e02,
            2.7666666e02, 3.7000000e02, 4.7666666e02, 5.9666656e02, 7.3000000e02,
            8.7666705e02, 1.0366667e03, 1.2099996e03, 1.3966665e03, 1.5966664e03,
            1.8100002e03, 2.0366663e03, 2.2766663e03, 2.5299995e03, 2.7966665e03,
            3.0766667e03, 3.3700000e03, 3.6766665e03, 3.9966660e03, 4.3300005e03,
            4.6766670e03, 5.0366665e03, 5.4099990e03, 5.7966660e03, 6.1966665e03,
            6.6099995e03, 7.0366665e03, 7.4766665e03, 7.9300000e03, 8.3966680e03,
            8.8766689e03, 9.3700088e03, 9.8766943e03, 1.0396724e04, 1.0930124e04,
            1.1476904e04, 1.2037088e04, 1.2610736e04, 1.3197907e04, 1.3798679e04,
            1.4413178e04, 1.5041558e04, 1.5684030e04, 1.6340859e04, 1.7012402e04,
            1.7699100e04, 1.8401496e04, 1.9120291e04, 1.9856332e04, 2.0610656e04,
            2.1384521e04, 2.2179449e04, 2.2997277e04, 2.3840172e04, 2.4710699e04,
            2.5611910e04, 2.6547354e04, 2.7521189e04, 2.8538248e04, 2.9604123e04,
            3.0725281e04, 3.1909119e04, 3.3164152e04, 3.4500062e04, 3.5927887e04,
            3.7460137e04, 3.9110980e04, 4.0896391e04, 4.2834340e04, 4.4945016e04,
            4.7251023e04, 4.9777590e04, 5.2552891e04, 5.5608223e04, 5.8978355e04,
            6.2701832e04, 6.6821242e04, 7.1383641e04, 7.6440891e04, 8.2050008e04,
        ], dtype=float)
    if grid == "theta":
        return np.array([
            1.9999998e01, 5.3333336e01, 1.0000004e02, 1.6000000e02, 2.3333333e02,
            3.2000000e02, 4.1999997e02, 5.3333337e02, 6.5999994e02, 7.9999994e02,
            9.5333368e02, 1.1200000e03, 1.3000002e03, 1.4933335e03, 1.7000000e03,
            1.9199995e03, 2.1533330e03, 2.3999998e03, 2.6599993e03, 2.9333330e03,
            3.2199998e03, 3.5199995e03, 3.8333335e03, 4.1600005e03, 4.4999995e03,
            4.8533335e03, 5.2199995e03, 5.5999995e03, 5.9933330e03, 6.3999995e03,
            6.8199995e03, 7.2533330e03, 7.6999995e03, 8.1600010e03, 8.6333398e03,
            9.1200068e03, 9.6200195e03, 1.0133368e04, 1.0660079e04, 1.1200161e04,
            1.1753639e04, 1.2320546e04, 1.2900935e04, 1.3494881e04, 1.4102478e04,
            1.4723879e04, 1.5359236e04, 1.6008815e04, 1.6672902e04, 1.7351900e04,
            1.8046291e04, 1.8756703e04, 1.9483887e04, 2.0228775e04, 2.0992527e04,
            2.1776508e04, 2.2582393e04, 2.3412162e04, 2.4268180e04, 2.5153225e04,
            2.6070588e04, 2.7024109e04, 2.8018262e04, 2.9058227e04, 3.0150018e04,
            3.1300535e04, 3.2517711e04, 3.3810594e04, 3.5189523e04, 3.6666238e04,
            3.8254027e04, 3.9967926e04, 4.1824852e04, 4.3843832e04, 4.6046207e04,
            4.8455832e04, 5.1099348e04, 5.4006426e04, 5.7210016e04, 6.0746703e04,
            6.4656957e04, 6.8985523e04, 7.3781766e04, 7.9100016e04, 8.5000000e04,
        ], dtype=float)
    raise ValueError(f"Unknown atmosphere grid '{grid}'")


def get_coords_dict(dims, coords, no_samples, max_atm_lev):
    # Build coordinate dictionary for monthly DataArray creation; used by um_mon_mn_sbatch.py.
    coords_dict = {}
    for dim in dims:
        if dim in ["time", "time_hrly", "time_daily"]:
            coord = coords["time"][:no_samples]
        elif dim == "surface_tiles":
            coord = [
                "BrDe", "BrEvTr", "BrEvTe", "NeDe", "NeEv", "C3Gr", "C3Cr", "C3Pa",
                "C4Gr", "C4Cr", "C4Pa", "ShDe", "ShEv", "Urban", "Lake", "Soil",
            ]
        elif dim == "depth":
            coord = coords["depth"]
        elif dim == "PFTs":
            coord = [
                "BrDe", "BrEvTr", "BrEvTe", "NeDe", "NeEv", "C3Gr", "C3Cr", "C3Pa",
                "C4Gr", "C4Cr", "C4Pa", "ShDe", "ShEv",
            ]
        elif dim == "rho_lev":
            coord = _atm_coords("rho")[:max_atm_lev]
        elif dim == "theta_lev":
            coord = _atm_coords("theta")[:max_atm_lev]
        elif dim == "latitude":
            coord = coords["latitude"]
        elif dim == "longitude":
            coord = coords["longitude"]
        elif dim == "lat_p":
            coord = coords["latitude"]
        elif dim == "lon_p":
            coord = coords["longitude"]
        elif dim == "p_levs":
            coord = coords["air_pressure"]
        elif dim == "band":
            coord = np.arange(1, 7)
        else:
            raise ValueError(f"Unsupported coordinate dimension '{dim}'")

        coords_dict[dim] = coord
    return coords_dict


def coord_attrs(coordname, startyr):
    # Return coordinate attributes for monthly outputs; used by um_mon_mn_sbatch.py.
    if re.search(r"_\d+$", coordname):
        coordname = re.sub(r"\d+$", "", coordname)

    attrs = {
        "time": {
            "long_name": "time",
            "units": f"days since {startyr}-01-01 00:00:00",
            "calendar": "360_day",
            "time_origin": f"01-JAN-{startyr}:00:00:00",
        },
        "time_hrly": {
            "long_name": "time",
            "units": f"days since {startyr}-01-01 00:00:00",
            "calendar": "360_day",
            "time_origin": f"01-JAN-{startyr}:00:00:00",
        },
        "time_daily": {
            "long_name": "time",
            "units": f"days since {startyr}-01-01 00:00:00",
            "calendar": "360_day",
            "time_origin": f"01-JAN-{startyr}:00:00:00",
        },
        "surface_tiles": {"long_name": "Surface Tile Names"},
        "band": {"long_name": "Shortwave Radiation Band Number"},
        "depth": {"long_name": "Soil Layer Mid-Depths", "units": "m"},
        "PFTs": {"long_name": "TRIFFID Plant Functional Types"},
        "rho_lev": {"long_name": "Height of Atmosopheric Rho Coordinate", "units": "m"},
        "theta_lev": {"long_name": "Height of Atmosopheric Theta Coordinate", "units": "m"},
        "latitude": {
            "long_name": "latitude",
            "short_name": "latitude",
            "units": "degrees_north",
            "point_spacing": "even",
        },
        "longitude": {
            "long_name": "longitude",
            "short_name": "longitude",
            "units": "degrees_east",
            "point_spacing": "even",
            "modulo": " ",
        },
        "lat_p": {"long_name": "Latitude for P Lev/UV Grid", "units": "degrees_north"},
        "lon_p": {"long_name": "Longitude for P Lev/UV Grid", "units": "degrees_east"},
        "p_levs": {"long_name": "Pressure Levels for P Lev/UV Grid", "units": "hPa"},
    }
    return attrs[coordname]


def resolve_coord_conflicts(existing_ds, coords_dict, dims):
    # Avoid coordinate-name collisions when appending to existing monthly files; used by um_mon_mn_sbatch.py.
    for base in ["time_hrly", "rho_lev", "theta_lev"]:
        if base not in coords_dict:
            continue

        existing = [name for name in existing_ds.coords if base in str(name)]
        existing_lengths = [len(existing_ds[name].data) for name in existing]
        if existing and len(coords_dict[base]) not in existing_lengths:
            new_name = f"{base}_{len(existing) + 1}"
            coords_dict[new_name] = coords_dict.pop(base)
            dims[dims.index(base)] = new_name

    return coords_dict, dims


def monthly_mean_from_dataarray(xda, no_yrs):
    # Compute strict whole-year monthly mean blocks from extracted arrays; used by um_mon_mn_sbatch.py.
    if no_yrs <= 0:
        raise ValueError("Number of years must be positive")

    if xda.shape[0] % no_yrs != 0:
        raise ValueError(
            f"Time axis length {xda.shape[0]} is not divisible by number of years {no_yrs}"
        )

    no_samples = xda.shape[0] // no_yrs
    new_shape = (no_yrs, no_samples, -1, *xda.shape[-2:])
    mean_data = np.reshape(xda.values.squeeze(), new_shape).squeeze().mean(axis=0)
    return mean_data, no_samples



