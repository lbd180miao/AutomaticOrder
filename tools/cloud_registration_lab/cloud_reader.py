"""Isolate native point-cloud IO failures from the interactive window."""
import json
import sys
from pathlib import Path
import open3d as o3d
from registration import load_cloud

if __name__ == '__main__':
    source, unit, directory = sys.argv[1:]
    cloud, info = load_cloud(source, unit)
    output = Path(directory)
    if not o3d.io.write_point_cloud(str(output/'cloud.ply'), cloud):
        raise OSError('无法写入临时点云')
    (output/'info.json').write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
