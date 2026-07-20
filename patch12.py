import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')
new_lines = []
skip = False
for i, line in enumerate(lines):
    if "res-iou" in line or "res-score" in line:
        continue
    if "<td>交并比(IoU):</td>" in line or "<td>综合得分:</td>" in line:
        # We need to skip this line and the surrounding <tr></tr>.
        # But wait, we can just filter them based on simple logic or regex.
        pass
    new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.write('\n'.join(new_lines))
print("Done global table partly")
