import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split('\n')
new_lines = []
for line in lines:
    if "iou-detail" in line or "score-detail" in line:
        continue
    new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.write('\n'.join(new_lines))
print("Done JS detail")
