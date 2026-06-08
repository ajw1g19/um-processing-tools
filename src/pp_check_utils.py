import json
import os
import tempfile
import time

import yaml

from pathlib import Path


# --- State file helpers ---


def load_state(path):
    # Load pp_check state JSON; returns empty dict if file is absent or unreadable.
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def state_write(path, data):
    # Write pp_check state JSON atomically via temp-file replace.
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=str(p.parent), delete=False) as tf:
        json.dump(data, tf, indent=2, sort_keys=True)
        tf.flush()
        try:
            os.fsync(tf.fileno())
        except OSError:
            pass
        tmpname = tf.name
    os.replace(tmpname, str(p))


# --- PP file helpers ---


def newest_pp_time(suite_dir):
    # Return the newest mtime (float epoch) among all .pp files under suite_dir,
    # or None if no .pp files are found.
    newest = 0.0
    for dirpath, _, filenames in os.walk(suite_dir):
        for fn in filenames:
            if fn.endswith(".pp"):
                try:
                    m = os.path.getmtime(os.path.join(dirpath, fn))
                except OSError:
                    continue
                if m > newest:
                    newest = m
    return newest if newest > 0.0 else None


def iso(ts):
    # Format an epoch timestamp as an ISO-8601 UTC string.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# --- Config helper ---


def load_pp_check_config():
    # Load Globus endpoint and path config from config/pp_check_config.yaml.
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "pp_check_config.yaml"
    )
    with open(config_path) as fh:
        return yaml.safe_load(fh) or {}


# --- sbatch writer ---


def write_sbatch_pp_check(
    fname,
    suite,
    since,
    logfile,
    workers=32,
    template_path=None,
    account="mh_gsp",
    partition="standard",
    qos="high",
    walltime="12:00:00",
    mem_per_cpu="5G",
    module_load="jaspy",
    python="python",
    root_dir=None,
    worker_path=None,
):
    # Render a pp_check sbatch script from config/pp_check_sbatch_template.sh.
    if root_dir is None:
        root_dir = os.path.dirname(os.path.dirname(__file__))
    if template_path is None:
        template_path = os.path.join(root_dir, "config", "pp_check_sbatch_template.sh")
    if worker_path is None:
        worker_path = os.path.join(root_dir, "check_pp_readable.py")

    model_output_root = os.path.join(os.path.dirname(root_dir), "Model_Output")

    with open(template_path, "r") as fh:
        template = fh.read()

    values = {
        "account": account,
        "partition": partition,
        "qos": qos,
        "walltime": walltime,
        "output": logfile,
        "mem_per_cpu": mem_per_cpu,
        "workers": workers,
        "module_load": module_load,
        "python": python,
        "work_dir": root_dir,
        "worker_path": worker_path,
        "suite": suite,
        "since": since,
        "model_output_root": model_output_root,
    }

    content = template.format_map(values)
    with open(fname, "w") as sbatch_file:
        sbatch_file.write(content)
