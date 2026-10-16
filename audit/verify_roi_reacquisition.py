"""Read-only replay of the two field packages using recipe 12's saved ROIs."""
import json
import sqlite3
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apps.vision.rack_camera_points import camera_pointmap_measurement


def main():
    with sqlite3.connect((ROOT / 'db.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        config = json.loads(db.execute(
            'select roi_config from vision_racklocationrecipe where id=12'
        ).fetchone()[0])['dual_point']
    report = {'recipe_id': 12, 'config': config, 'frames': {}}
    for suffix in ('080935', '081232'):
        folder = ROOT / '3d_SDK' / 'pic' / ('2026-10-15_POS1_L1_' + suffix)
        result = camera_pointmap_measurement(
            cv2.imread(str(folder / 'image2d.png'), cv2.IMREAD_GRAYSCALE),
            np.load(folder / 'pointcloud.npy'), config,
            json.loads((folder / 'metadata.json').read_text(encoding='utf-8')))
        report['frames'][folder.name] = result
        print(folder.name, result['success'], result.get('errorCode'),
              [(line['target'], line['valid_count'], line.get('edge_shift_px'))
               for line in result.get('lines', [])])
    output = ROOT / 'audit' / 'roi_reacquisition_verification.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert all(result['success'] for result in report['frames'].values()), str(output)


if __name__ == '__main__':
    main()
