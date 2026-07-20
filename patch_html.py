import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target1 = '''            <label>最低得分<input id="foam-min-score" type="number" min="0" max="1" step="0.01" value="0.8"></label>
            <label>最低 IoU<input id="foam-min-iou" type="number" min="0" max="1" step="0.01" value="0.7"></label>'''
replace1 = ""

target2 = '''  const scoreThreshold = thresh.score_threshold ?? thresh.minScore ?? 0.80;
  const iouThreshold = thresh.iou_threshold ?? thresh.minIoU ?? 0.70;'''
replace2 = ""

target3 = '''  document.getElementById('recipe-thresholds').textContent = 
    覆盖率≥, 得分≥, IoU≥;'''
replace3 = '''  document.getElementById('recipe-thresholds').textContent = 
    覆盖率≥;'''

target4 = '''  document.getElementById('foam-min-score').value = scoreThreshold;
  document.getElementById('foam-min-iou').value = iouThreshold;'''
replace4 = ""

target5 = '''    score_threshold: Number(document.getElementById('foam-min-score').value || 0.80),
    iou_threshold: Number(document.getElementById('foam-min-iou').value || 0.70),'''
replace5 = ""

target6 = '''            <tr>
              <td>交并比(IoU):</td>
              <td id="res-iou"></td>
            </tr>
            <tr>
              <td>综合得分:</td>
              <td id="res-score"></td>
            </tr>'''
replace6 = ""

target7 = '''        document.getElementById('res-iou').textContent = sideData.iou ? ${(sideData.iou * 100).toFixed(1)}% : '--';
        document.getElementById('res-score').textContent = sideData.score ? sideData.score.toFixed(3) : '--';'''
replace7 = ""

for t, r in [(target1, replace1), (target2, replace2), (target3, replace3), (target4, replace4), (target5, replace5), (target6, replace6), (target7, replace7)]:
    if t in content:
        content = content.replace(t, r)
        print("Patched target")
    else:
        print("Target not found:\n" + t[:100])

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done html")
