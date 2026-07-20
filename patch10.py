import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target1 = '''              <tr>
                <td style="color:#6b7280;"><strong>交并比(IoU):</strong></td>
                <td id="left-iou-detail" style="font-family:monospace;">-</td>
              </tr>
              <tr>
                <td style="color:#6b7280;"><strong>综合得分:</strong></td>
                <td id="left-score-detail" style="font-family:monospace;">-</td>
              </tr>'''
replace1 = ""

target2 = '''              <tr>
                <td style="color:#6b7280;"><strong>交并比(IoU):</strong></td>
                <td id="right-iou-detail" style="font-family:monospace;">-</td>
              </tr>
              <tr>
                <td style="color:#6b7280;"><strong>综合得分:</strong></td>
                <td id="right-score-detail" style="font-family:monospace;">-</td>
              </tr>'''
replace2 = ""

target3 = '''    document.getElementById('left-iou-detail').innerHTML = <span style="color:#10b981;">%</span>;
    document.getElementById('left-score-detail').innerHTML = <span style="color:#10b981;"></span>;'''
replace3 = ""

target4 = '''    document.getElementById('right-iou-detail').innerHTML = <span style="color:#10b981;">%</span>;
    document.getElementById('right-score-detail').innerHTML = <span style="color:#10b981;"></span>;'''
replace4 = ""


# Also remove 交并比(IoU) and 综合得分 from #foam-results-table if it was not fully removed.
target5 = '''            <tr>
              <td>交并比(IoU):</td>
              <td id="res-iou"></td>
            </tr>
            <tr>
              <td>综合得分:</td>
              <td id="res-score"></td>
            </tr>'''
replace5 = ""

target6 = '''        document.getElementById('res-iou').textContent = sideData.iou ? ${(sideData.iou * 100).toFixed(1)}% : '--';
        document.getElementById('res-score').textContent = sideData.score ? sideData.score.toFixed(3) : '--';'''
replace6 = ""

targets = [target1, target2, target3, target4, target5, target6]
replaces = [replace1, replace2, replace3, replace4, replace5, replace6]

for t, r in zip(targets, replaces):
    if t in content:
        content = content.replace(t, r)
        print("Patched target")
    else:
        print("Target not found: " + t[:50].replace('\n', ' '))

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done html table")
