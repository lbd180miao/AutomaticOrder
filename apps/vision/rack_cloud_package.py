"""Read saved capture data for point-cloud template matching."""
import json
from pathlib import Path

import cv2
import numpy as np


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def load_package(path):
    path = Path(path)
    image_path = path/'image2d.png'
    image = cv2.imdecode(np.fromfile(image_path, np.uint8), cv2.IMREAD_COLOR) if image_path.is_file() else None
    def array(name):
        return np.load(path/name, allow_pickle=False) if (path/name).is_file() else None
    return {'image': image, 'cloud': array('pointcloud.npy'),
            'metadata': read_json(path/'metadata.json') if (path/'metadata.json').is_file() else {},
            'config': read_json(path/'roi_config.json') if (path/'roi_config.json').is_file() else {},
            'hand_eye': array('hand_eye_matrix.npy'), 'robot_pose': array('robot_pose_matrix.npy'),
            'pixel_index_map': array('pixel_index_map.npy')}
