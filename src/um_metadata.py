import os
import re
import yaml

# Metadata helpers for UM variables and derived outputs (daily, hourly, SW band).


def _load_yaml(path):
    # Internal loader used by metadata lookups in this module.
    with open(path, "r") as handle:
        return yaml.safe_load(handle) or {}


def _config_dir(config_dir=None):
    # Resolve config directory for metadata files; used by get_metadata.
    if config_dir:
        return config_dir
    root_dir = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(root_dir, "config")


def _meta_um(varname, config_dir=None):
    # Resolve default metadata from config YAML; used by um_extract_sbatch.py.
    cfg_dir = _config_dir(config_dir)
    um_to_varname = _load_yaml(os.path.join(cfg_dir, "um_varnames.yaml"))
    um_meta = _load_yaml(os.path.join(cfg_dir, "um_meta.yaml"))

    if varname.startswith("UM_"):
        key = um_to_varname.get(varname)
        if key is None:
            raise KeyError(f"No mapping for UM variable '{varname}'")
        metadata = um_meta.get(key)
        if metadata is None:
            raise KeyError(f"No metadata for variable '{key}'")
        return key, metadata

    metadata = um_meta.get(varname)
    if metadata is None:
        raise KeyError(f"No metadata for variable '{varname}'")
    return varname, metadata


def _meta_um_hourly(varname):
    # Resolve hourly metadata set; used by um_extract_sbatch.py and um_mon_mn_sbatch.py.
    um_to_varname = {
        "UM_m01s00i024_vn1302": "ts_hrly",
        "UM_m01s01i201_vn1302": "net_ssw_hrly",
        "UM_m01s01i208_vn1302": "toa_sw_out_hrly",
        "UM_m01s02i201_vn1302": "net_slw_hrly",
        "UM_m01s03i236_vn1302": "tas_hrly",
        "UM_m01s03i332_vn1302": "toa_lw_out_hrly",
        "UM_m01s04i203_vn1302": "ls_rain_hrly",
        "UM_m01s04i204_vn1302": "ls_snow_hrly",
        "UM_m01s05i205_vn1302": "conv_rain_hrly",
        "UM_m01s05i206_vn1302": "conv_snow_hrly",
        "UM_m01s05i216_vn1302": "pr_hrly",
        "UM_m01s05i269_vn1302": "deep_ind_hrly",
        "UM_m01s05i272_vn1302": "midlev_ind_hrly",
        "UM_m01s05i277_vn1302": "deep_precip_hrly",
        "UM_m01s05i279_vn1302": "midlev_precip_hrly",
    }

    meta_dict = {
        "ts_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Surface Temperature",
                "standard_name": "surface_temperature",
                "units": "K",
            },
            "convert": "temp",
        },
        "net_ssw_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Net Downward Surface SW Radiation",
                "standard_name": "surface_net_downward_shortwave_flux",
                "units": "W m-2",
            },
        },
        "toa_sw_out_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of TOA Outgoing Radiation",
                "standard_name": "toa_outgoing_shortwave_flux",
                "units": "W m-2",
            },
        },
        "net_slw_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Net Downward Surface LW Radiation",
                "standard_name": "surface_net_downward_longwave_flux",
                "units": "W m-2",
            },
        },
        "tas_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Surface Air Temperature",
                "standard_name": "air_temperature",
                "units": "K",
                "height": "1.5 m",
            },
            "convert": "temp",
        },
        "toa_lw_out_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of TOA Outgoing LW Radiation",
                "standard_name": "toa_outgoing_longwave_flux",
                "units": "W m-2",
            },
        },
        "ls_rain_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Large-Scale Rainfall",
                "standard_name": "stratiform_rainfall_flux",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
        "ls_snow_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Large-Scale Snowfall",
                "standard_name": "stratiform_snowfall_flux",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
        "conv_rain_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Convective Rainfall",
                "standard_name": "convective_rainfall_flux",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
        "conv_snow_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Convective Snowfall",
                "standard_name": "convective_snowfall_flux",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
        "pr_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Total Precipitation",
                "standard_name": "precipitation_flux",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
        "deep_ind_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {"long_name": "Diurnal Cycle of Deep Convection Indicator"},
        },
        "midlev_ind_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {"long_name": "Diurnal Cycle of Mid-Level Convection Indicator"},
        },
        "deep_precip_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Deep Convective Precipitation",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
        "midlev_precip_hrly": {
            "dims": ["time_hrly", "latitude", "longitude"],
            "attrs": {
                "long_name": "Diurnal Cycle of Mid-Level Convective Precipitation",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
    }

    if varname.startswith("UM_"):
        key = um_to_varname.get(varname)
        if key is None:
            raise KeyError(f"No hourly mapping for UM variable '{varname}'")
        return key, meta_dict[key]

    if varname not in meta_dict:
        raise KeyError(f"No hourly metadata for variable '{varname}'")
    return varname, meta_dict[varname]


def _meta_um_daily(varname):
    # Resolve daily metadata set; used by um_extract_sbatch.py and um_mon_mn_sbatch.py.
    um_to_varname = {
        "UM_m01s00i024_vn1302": "ts_daily",
        "UM_m01s03i236_vn1302": "tas_daily",
        "UM_m01s04i203_vn1302": "ls_rain_daily",
        "UM_m01s05i205_vn1302": "conv_rain_daily",
        "UM_m01s05i216_vn1302": "pr_daily",
    }

    meta_dict = {
        "ts_daily": {
            "dims": ["time_daily", "latitude", "longitude"],
            "attrs": {
                "long_name": "Daily Surface Temperature",
                "standard_name": "surface_temperature",
                "units": "K",
            },
            "convert": "temp",
        },
        "tas_daily": {
            "dims": ["time_daily", "latitude", "longitude"],
            "attrs": {
                "long_name": "Daily Surface Air Temperature",
                "standard_name": "air_temperature",
                "units": "K",
                "height": "1.5 m",
            },
            "convert": "temp",
        },
        "ls_rain_daily": {
            "dims": ["time_daily", "latitude", "longitude"],
            "attrs": {
                "long_name": "Daily Large-Scale Rainfall",
                "standard_name": "stratiform_rainfall_flux",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
        "conv_rain_daily": {
            "dims": ["time_daily", "latitude", "longitude"],
            "attrs": {
                "long_name": "Daily Convective Rainfall",
                "standard_name": "convective_rainfall_flux",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
        "pr_daily": {
            "dims": ["time_daily", "latitude", "longitude"],
            "attrs": {
                "long_name": "Daily Total Precipitation",
                "standard_name": "precipitation_flux",
                "units": "kg m-2 s-1",
            },
            "convert": "precip",
        },
    }

    if varname.startswith("UM_"):
        key = um_to_varname.get(varname)
        if key is None:
            raise KeyError(f"No daily mapping for UM variable '{varname}'")
        return key, meta_dict[key]

    if varname not in meta_dict:
        raise KeyError(f"No daily metadata for variable '{varname}'")
    return varname, meta_dict[varname]


def _meta_um_swband(varname, level=None):
    # Resolve shortwave-band metadata set; used by um_extract_sbatch.py and um_mon_mn_sbatch.py.
    def meta_dict(name, lev, rad_type):
        if rad_type == "up_sw_band":
            long_name = "Upwelling Shortwave Radiation on SW Bands"
        else:
            long_name = "Downwelling Shortwave Radiation on SW Bands"

        data = {
            f"surf_{rad_type}": {
                "dims": ["time", "band", "latitude", "longitude"],
                "attrs": {
                    "long_name": f"Surface {long_name}",
                    "units": "W m-2",
                },
            },
            f"toa_{rad_type}": {
                "dims": ["time", "band", "latitude", "longitude"],
                "attrs": {
                    "long_name": f"TOA {long_name}",
                    "units": "W m-2",
                },
            },
            f"lev{lev}_{rad_type}": {
                "dims": ["time", "band", "latitude", "longitude"],
                "attrs": {
                    "long_name": f"Level {lev} {long_name}",
                    "units": "W m-2",
                },
            },
        }
        return data[name]

    if varname.startswith("UM_"):
        if "509" in varname:
            rad_type = "up_sw_band"
        elif "510" in varname:
            rad_type = "down_sw_band"
        else:
            raise KeyError(f"No SW band mapping for UM variable '{varname}'")

        if level == 1:
            varname = f"surf_{rad_type}"
        elif level == 86:
            varname = f"toa_{rad_type}"
        else:
            varname = f"lev{level}_{rad_type}"

        return varname, meta_dict(varname, level, rad_type)

    if varname.startswith("lev"):
        level = int("".join(re.findall(r"\d+", varname.split("_")[0])))
    elif varname.startswith("surf"):
        level = 1
    elif varname.startswith("toa"):
        level = 86

    rad_type = varname.split("_", 1)[1]
    return varname, meta_dict(varname, level, rad_type)


def get_metadata(varname, package_name, level=None, config_dir=None):
    # Public metadata router used by um_extract_sbatch.py and um_stash_extract_funcs.py.
    if "hourly" in package_name:
        return _meta_um_hourly(varname)
    if "daily" in package_name:
        return _meta_um_daily(varname)
    if "swband" in package_name:
        return _meta_um_swband(varname, level=level)
    return _meta_um(varname, config_dir=config_dir)
