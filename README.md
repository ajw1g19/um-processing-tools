# STASH Processing

Programs for extraction and processing of Unified Model output

This directory contains five workflows:

- Confirming file transfer from ARCHER2 and PP readability checks.
- Sorting model output files into expected cycle directories.
- STASH extraction for one package or custom request list.
- Bulk climate extraction (multiple predefined packages in one run).
- Monthly-mean processing from extracted NetCDF files.

## Directory Layout

### config/

- packages.yaml: Named STASH packages and version-dependent rules.
- pp_check_config.yaml: Globus endpoint and archive-path settings for PP transfer checks.
- pp_check_state.json: Last-seen per-suite .pp mtime state used to detect newly transferred files.
- pp_check_sbatch_template.sh: sbatch template used for PP readability check jobs.
- um_stash_vn.yaml: Suite-to-STASH-version mapping.
- stash.xlsx: STASH lookup tables, one sheet per version (for example stash_v1, stash_v2.1, stash_v5).
- um_varnames.yaml: UM variable name mapping used in metadata handling.
- um_meta.yaml: Variable metadata used when writing NetCDF outputs.
- sbatch_template.sh: Shared sbatch template used by job writers.

### run/

- stash_extract/: YAML configs for extraction jobs.
- monthly_mean/: YAML configs for monthly-mean jobs.
- pp_check/: temporary PP readability-check outputs.
- sbatch_scripts/: sbatch scripts for all workflows.
- logs/: log files for all workflows.

Use tidy_run_files.sh to clean subdirectories inside run/

## Workflow: submit_pp_checks.py

Submits PP readability-check jobs only for suites with newly arrived .pp files,
then updates suite state when jobs are submitted.

Run:

python STASH_Processing/submit_pp_checks.py

Inputs:

- submit confirmation (y/n) after planned jobs are listed

Generated files:

- Sbatch scripts (one per suite with new files):
  - STASH_Processing/run/sbatch_scripts/{suite}\_pp_check.sbatch
- Log files:
  - STASH_Processing/run/logs/{suite}\_pp_check.{slurm_job_id}.out

Updated files:

- State file:
  - STASH_Processing/config/pp_check_state.json

Worker used:

- STASH_Processing/check_pp_readable.py

## Workflow: sort_model_output.py

Interactive cleanup of Model_Output suite directories before extraction.
This workflow renames p1 files to pm, moves misplaced pp files into the expected
cycle folder, moves restart dumps to a dedicated restart_dumps directory, and
deletes checksum files.

Run:

python STASH_Processing/sort_model_output.py

Inputs:

- suite
- start year and end year (end exclusive)

Output updates:

- In-place file moves/renames under Model_Output/{suite}/
- Restart dumps moved to Model_Output/{suite}/restart_dumps/

Use clean_restart_dumps.py to remove quarterly restart dumps (months 04, 07, 10)
from Model_Output/{suite}/restart_dumps/
Useful for reclaiming disk space when long model integrations have finished

## Workflow: stash_extraction.py

Interactive extraction driver for one package or custom STASH list.

Run:

python STASH_Processing/stash_extraction.py

Inputs:

- suite
- start year and end year (end exclusive)
- either package name or custom 5-digit STASH codes
- job walltime

Generated files:

- Extraction config YAML:
  - STASH_Processing/run/stash_extract/{suite}\_{package}\_{start}\_{end}.yaml
- Sbatch script:
  - STASH_Processing/run/sbatch_scripts/{suite}\_{package}\_{start}\_{end}.sbatch
- Log file:
  - STASH_Processing/run/logs/{suite}\_{package}\_{start}-{end}.out

Worker used:

- STASH_Processing/um_extract_sbatch.py

Output data location:

- Processed_Output/{suite}/{varname}\_{start}01-{end-1}12.nc

### How STASH Version Resolution Works

STASH requests are resolved in two steps:

1. um_stash_vn.yaml selects which STASH version applies to the suite and requested years.
2. That version is used to select the corresponding sheet in stash.xlsx (sheet name stash_v{version}).

#### Single-version format

If a suite always uses one version:

```yaml
u-dt829: 5
```

#### Multi-version format

If a suite changes version over time, use year-keyed entries:

```yaml
u-example:
  "1850": 4
  "1900": 5
```

This means 1850-1899 uses version 4 and 1900 onward uses version 5.
Requested periods must stay within one interval; a request that spans intervals is rejected.

## Workflow: extract_climate.py

Special-case extraction driver built on the same YAML/sbatch workflow as stash_extraction.py.
It submits a fixed package set for one suite/time window.

Run:

python STASH_Processing/extract_climate.py

Default package set:

- spinup, surfacefrac, soil-moisture, soil-cn, veg, productivity, surfrad, precip, wind, pressure

Generated files (one per package):

- Extraction config YAML:
  - STASH_Processing/run/stash_extract/{suite}\_{package}\_{start}\_{end}.yaml
- Sbatch script:
  - STASH_Processing/run/sbatch_scripts/{suite}\_{package}\_{start}\_{end}.sbatch
- Log file:
  - STASH_Processing/run/logs/{suite}\_{package}\_{start}-{end}.out

Worker used:

- STASH_Processing/um_extract_sbatch.py

Output data location:

- Processed_Output/{suite}/{varname}\_{start}01-{end-1}12.nc

## Workflow: stash_mon_mn.py

Interactive monthly-mean driver that processes extracted files and writes one consolidated file per suite-period.

Run:

python STASH_Processing/stash_mon_mn.py

Inputs:

- suite
- start year and end year (end exclusive; strict whole-year blocks)
- optional overwrite selection for variables already present
- job walltime

Generated files:

- Monthly config YAML:
  - STASH_Processing/run/monthly_mean/{suite}\_mon_mn\_{start}-{end}.yaml
- Sbatch script:
  - STASH_Processing/run/sbatch_scripts/{suite}\_mon_mn\_{start}-{end}.sbatch
- Log file:
  - STASH_Processing/run/logs/{suite}\_mon_mn\_{start}-{end}.out

Worker used:

- STASH_Processing/um_mon_mn_sbatch.py

Output data location:

- Monthly_Means_Files/{suite}\_monthly_means\_{start}01-{end-1}12.nc

Notes:

- Existing consolidated monthly files can be updated in-place by replacing selected variables.
- Monthly variable naming/metadata is preserved via config/um_varnames.yaml and config/um_meta.yaml.
