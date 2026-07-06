#!/bin/bash

#SBATCH --account={account}
#SBATCH --partition={partition}
#SBATCH --qos={qos}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={workers}
#SBATCH --time={walltime}
#SBATCH --output={output}
#SBATCH --mem-per-cpu={mem_per_cpu}

module load {module_load}

# The submitting shell's environment is inherited (Slurm default --export=ALL) and
# may carry a stale UDUNITS2_XML_PATH from another jaspy version. Left set, it makes
# cfunits fail to load its units database, so `import cf` dies with an Sv assertion
# for every file. Unset it so cfunits uses its own bundled, self-consistent database.
unset UDUNITS2_XML_PATH

cd {work_dir}

{python} {worker_path} {suite} --since {since} --workers {workers} --root {model_output_root}
