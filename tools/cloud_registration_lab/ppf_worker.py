"""Run OpenCV-contrib PPF outside the GUI and the application's cv2 environment."""
import json
import sys
from pathlib import Path

runtime = Path(__file__).with_name('.ppf_runtime')
sys.path.insert(0, str(runtime))
import numpy as np
import cv2


def main():
    cv2.setNumThreads(2)
    directory = Path(sys.argv[1])
    if not hasattr(cv2, 'ppf_match_3d_PPF3DDetector'):
        raise RuntimeError('缺少 PPF 模块，请运行 install_ppf.bat 安装独立依赖')
    model = np.array(np.load(directory/'model.npy', mmap_mode='r', allow_pickle=False), dtype=np.float32)
    scene = np.array(np.load(directory/'scene.npy', mmap_mode='r', allow_pickle=False), dtype=np.float32)
    detector = cv2.ppf_match_3d_PPF3DDetector(0.04, 0.05, 30)
    detector.trainModel(model)
    poses = detector.match(scene, 0.2, 0.04)
    output = []
    for pose in sorted(poses, key=lambda p: p.numVotes, reverse=True)[:60]:
        matrix = np.asarray(pose.pose, dtype=float)
        if matrix.shape == (4, 4) and np.isfinite(matrix).all():
            output.append({'transform': matrix.tolist(), 'votes': int(pose.numVotes)})
    (directory/'poses.json').write_text(json.dumps(output, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
