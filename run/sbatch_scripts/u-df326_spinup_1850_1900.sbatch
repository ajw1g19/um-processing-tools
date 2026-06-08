#!/bin/bash

#SBATCH --account=mh_gsp
#SBATCH --partition=standard
#SBATCH --qos=high
#SBATCH --nodes=1
#SBATCH --ntasks=10
#SBATCH --time=00:40:00
#SBATCH --output=/gws/ssde/j25b/mh_gsp/STASH_extract/run/logs/u-df326_spinup_1850-1900.out
#SBATCH --mem-per-cpu=5G

module load jaspy

cd /gws/ssde/j25b/mh_gsp/STASH_extract

python /gws/ssde/j25b/mh_gsp/STASH_extract/um_extract_sbatch.py /gws/ssde/j25b/mh_gsp/STASH_extract/run/stash_extract/u-df326_spinup_1850_1900.yaml
