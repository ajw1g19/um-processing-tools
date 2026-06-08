#!/bin/bash

#SBATCH --account={account}
#SBATCH --partition={partition}
#SBATCH --qos={qos}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={ntasks}
#SBATCH --time={time}
#SBATCH --output={output}
#SBATCH --mem-per-cpu={mem_per_cpu}

module load {module_load}

cd {work_dir}

{python} {worker_path} {config_path}
