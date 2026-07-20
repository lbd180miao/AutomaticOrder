import sys
import re

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

content = re.sub(r'<tr>\s*<td>交并比\(IoU\):</td>\s*<td.*?></td>\s*</tr>', '', content)
content = re.sub(r'<tr>\s*<td>综合得分:</td>\s*<td.*?></td>\s*</tr>', '', content)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done regex")
