# STASH Extract

Programs for extraction and processing of Unified Model output

This directory contains three related workflows:

- STASH extraction for one package or custom request list.
- Bulk climate extraction (multiple predefined packages in one run).
- Monthly-mean processing from extracted NetCDF files.

## Directory Layout

### config/

- packages.yaml: Named STASH packages and version-dependent rules.
- um_stash_vn.yaml: Suite-to-STASH-version mapping.
- stash.xlsx: STASH lookup tables, one sheet per version (for example stash_v1, stash_v2.1, stash_v5).
- um_varnames.yaml: UM variable name mapping used in metadata handling.
- um_meta.yaml: Variable metadata used when writing NetCDF outputs.
- sbatch_template.sh: Shared sbatch template used by job writers.

### run/

- stash_extract/: YAML configs for extraction jobs.
- monthly_mean/: YAML configs for monthly-mean jobs.
- sbatch_scripts/: sbatch scripts for all workflows.
- logs/: log files for all workflows.

## How STASH Version Resolution Works

STASH requests are resolved in two steps:

1. um_stash_vn.yaml selects which STASH version applies to the suite and requested years.
2. That version is used to select the corresponding sheet in stash.xlsx (sheet name stash_v<version>).

### Single-version format

If a suite always uses one version:

```yaml
u-dt829: 5
```

### Multi-version format

If a suite changes version over time, use year-keyed entries:

```yaml
u-example:
  "1850": 4
  "1900": 5
```

This means 1850-1899 uses version 4 and 1900 onward uses version 5.
Requested periods must stay within one interval; a request that spans intervals is rejected.

## Workflow: stash_extraction.py

Interactive extraction driver for one package or custom STASH list.

Run:

python STASH_extract/stash_extraction.py

Inputs:

- suite
- start year and end year (end exclusive)
- either package name or custom 5-digit STASH codes
- job walltime

Generated files:

- Extraction config YAML:
  - STASH*extract/run/stash_extract/<suite>*<package>_<start>_<end>.yaml
- Sbatch script:
  - STASH*extract/run/sbatch_scripts/<suite>*<package>_<start>_<end>.sbatch
- Log file:
  - STASH*extract/run/logs/<suite>*<package>\_<start>-<end>.out

Worker used:

- STASH_extract/um_extract_sbatch.py

Output data location:

- Processed*Output/<suite>/<varname>*<start>01-<end-1>12.nc

## Workflow: extract_climate.py

Special-case extraction driver built on the same YAML/sbatch workflow as stash_extraction.py.
It submits a fixed package set for one suite/time window.

Run:

python STASH_extract/extract_climate.py

Default package set:

- spinup, surfacefrac, soil-moisture, soil-cn, veg, productivity, surfrad, precip, wind, pressure

Generated files (one per package):

- Extraction config YAML:
  - STASH*extract/run/stash_extract/<suite>*<package>_<start>_<end>.yaml
- Sbatch script:
  - STASH*extract/run/sbatch_scripts/<suite>*<package>_<start>_<end>.sbatch
- Log file:
  - STASH*extract/run/logs/<suite>*<package>\_<start>-<end>.out

Worker used:

- STASH_extract/um_extract_sbatch.py

Output data location:

- Processed*Output/<suite>/<varname>*<start>01-<end-1>12.nc

## Workflow: stash_mon_mn.py

Interactive monthly-mean driver that processes extracted files and writes one consolidated file per suite-period.

Run:

python STASH_extract/stash_mon_mn.py

Inputs:

- suite
- start year and end year (end exclusive; strict whole-year blocks)
- optional overwrite selection for variables already present
- job walltime

Generated files:

- Monthly config YAML:
  - STASH*extract/run/monthly_mean/<suite>\_mon_mn*<start>-<end>.yaml
- Sbatch script:
  - STASH*extract/run/sbatch_scripts/<suite>\_mon_mn*<start>-<end>.sbatch
- Log file:
  - STASH*extract/run/logs/<suite>\_mon_mn*<start>-<end>.out

Worker used:

- STASH_extract/um_mon_mn_sbatch.py

Output data location:

- Monthly*Means_Files/<suite>\_monthly_means*<start>01-<end-1>12.nc

Notes:

- Existing consolidated monthly files can be updated in-place by replacing selected variables.
- Monthly variable naming/metadata is preserved via config/um_varnames.yaml and config/um_meta.yaml.
