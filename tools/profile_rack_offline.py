"""Read-only offline registration profile; does not access PLC/cameras or write results."""
import argparse
import os
import sys
import json
import time
import cProfile
import pstats
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('package', type=Path)
parser.add_argument('--threads', type=int, default=1)
args = parser.parse_args()
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = str(args.threads) if name == 'OMP_NUM_THREADS' else '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from apps.vision.rack_cloud_match import match_template, add_display_pixels
folder = args.package
config = json.loads((folder / 'roi_config.json').read_text(encoding='utf-8-sig'))
metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8-sig'))
start = time.perf_counter()
cloud = np.load(folder / 'pointcloud.npy', allow_pickle=False)
print('load_seconds', round(time.perf_counter()-start, 3), 'shape', cloud.shape, flush=True)
import open3d
profiler = cProfile.Profile()
start = time.perf_counter()
profiler.enable()
result = match_template(cloud, metadata, config['cloud_center_reference'])
add_display_pixels(result, cloud, metadata)
profiler.disable()
print('threads', args.threads, 'compute_seconds', round(time.perf_counter()-start,3),
      'success', result['success'], 'points', result['points'], flush=True)
pstats.Stats(profiler).strip_dirs().sort_stats('cumtime').print_stats(18)

# Warm repeated measurements exclude imports and profiler overhead.
from statistics import median
samples = []
for _ in range(3):
    started = time.perf_counter()
    result = match_template(cloud, metadata, config['cloud_center_reference'])
    add_display_pixels(result, cloud, metadata)
    samples.append(time.perf_counter() - started)
print('warm_seconds', [round(value, 3) for value in samples],
      'median', round(median(samples), 3), flush=True)
