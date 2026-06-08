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

cd {work_dir}

{python} {worker_path} {suite} --since {since} --workers {workers} --root {model_output_root}
