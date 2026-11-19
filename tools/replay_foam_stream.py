"""Teach the supplied pic2 fixture, or replay arbitrary videos without PLC access."""
import argparse
import json
from pathlib import Path
import sys
import time

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apps.vision.algorithms.foam_stream import FoamStreamInspector, annotate


def teach_pic2(source, output):
    """Explicit manual teaching from two reviewed NORMAL frames, not auto-learning."""
    output.mkdir(parents=True, exist_ok=True)
    definitions = [
        ('far', 0, [(330,350,410,410),(535,350,620,400),(1125,300,1180,790),(570,420,610,640)],
         {'left':(75,455,420,700), 'right':(720,480,990,680)}),
        ('near', 38, [(140,230,190,300),(470,235,575,280),(550,375,600,670)],
         {'left':(20,425,310,720), 'right':(760,440,1150,730)}),
    ]
    capture = cv2.VideoCapture(str(source))
    views = []
    try:
        for name, index, anchors, regions in definitions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f'无法读取示教帧 {index}')
            frame = cv2.resize(frame, (1200,800))
            image_path = output / f'{name}.png'
            if not cv2.imwrite(str(image_path), frame):
                raise OSError(f'无法保存 {image_path}')
            ratio = lambda box: [v/d for v,d in zip(box,(1200,800,1200,800))]
            views.append(dict(name=name,image=image_path.name,anchors=[ratio(b) for b in anchors],
                              regions={s:ratio(b) for s,b in regions.items()}))
    finally:
        capture.release()
    profile = {'version':1, 'name':'pic2 灰色泡棉 / 双观察位置', 'width':1200,
               'scope':'仅用于已示教的 pic2 料架及相近拍摄条件；其他产品需要重新示教',
               'temporal':{'confirm_frames':3,'confirm_seconds':.3,'max_gap':1.0}, 'views':views}
    path = output / 'profile.json'
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2),encoding='utf-8')
    return path


def replay(source, profile, output):
    detector = FoamStreamInspector(profile)
    capture = cv2.VideoCapture(str(source))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not capture.isOpened() or not 0 < fps <= 240:
        capture.release()
        raise ValueError(f'无效视频或帧率：{source}')
    output.mkdir(parents=True, exist_ok=True)
    writer = None
    rows = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            index = len(rows)
            result = detector.process(frame, timestamp=index/fps, frame_id=index)
            rows.append(result)
            display = cv2.resize(frame, (1200,round(frame.shape[0]*1200/frame.shape[1])))
            display = annotate(display, result)
            if writer is None:
                writer = cv2.VideoWriter(str(output/f'{source.stem}_detected.mp4'),
                                         cv2.VideoWriter_fourcc(*'mp4v'), fps, display.shape[1::-1])
                if not writer.isOpened():
                    raise OSError('无法创建结果视频')
            writer.write(display)
            if index % 30 == 0 or any(abs(t-index/fps) < 1e-5 for t in result['first_ng'].values()):
                cv2.imwrite(str(output/f'{source.stem}_{index:04d}.jpg'), display)
    finally:
        capture.release()
        if writer is not None:
            writer.release()
    summary = {'video':source.name,'frames':len(rows),'fps':fps,
               'first_ng':rows[-1]['first_ng'] if rows else {},
               'invalid_registration_frames':sum(r['registration']['status']=='INVALID' for r in rows),
               'mean_algorithm_ms':round(sum(r['elapsed_ms'] for r in rows)/max(1,len(rows)),2),
               'note':'开发素材回放，非独立验收准确率；调试流程不连接 PLC。'}
    (output/f'{source.stem}.json').write_text(json.dumps({'summary':summary,'frames':rows},
                                         ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--teach-pic2', type=Path)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--videos', nargs='*', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'tmp/foam_stream_results')
    args = parser.parse_args()
    cv2.setNumThreads(2)
    if args.teach_pic2:
        teach_pic2(args.teach_pic2, args.profile.parent)
    for source in args.videos or []:
        replay(source, args.profile, args.output)
