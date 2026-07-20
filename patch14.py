import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target1 = '''              <tr>
                <td style="color:#6b7280;"><strong>交并比(IoU):</strong></td>
              </tr>'''
replace1 = ""

target2 = '''              <tr>
                <td style="color:#6b7280;"><strong>综合得分:</strong></td>
                <td id="left-score" style="font-family:monospace;font-weight:700;">-</td>
              </tr>'''
replace2 = ""

target3 = '''              <tr>
                <td style="color:#6b7280;"><strong>综合得分:</strong></td>
                <td id="right-score" style="font-family:monospace;font-weight:700;">-</td>
              </tr>'''
replace3 = ""

target4 = '''<small>每个配方的左/右 ROI 框即为标准区域，IoU 实时计算，<br>无需额外配置。画好 ROI 后直接检测即可。</small>'''
replace4 = '''<small>每个配方的左/右 ROI 框即为标准区域，<br>无需额外配置。画好 ROI 后直接检测即可。</small>'''

target5 = '''<div class="detail-chip">综合得分 <strong id="d-score">-</strong></div>'''
replace5 = ""

target6 = '''document.getElementById('d-score').textContent = Number(r.score).toFixed(3);'''
replace6 = ""

for t, r in [(target1, replace1), (target2, replace2), (target3, replace3), (target4, replace4), (target5, replace5), (target6, replace6)]:
    content = content.replace(t, r)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done html table TR")
