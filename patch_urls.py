
import os
path = 'D:/workspace2/AutomaticOrder/apps/coordinates/urls.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('views.api_capture_real, name=\'api_capture_real\'', 'views.api_capture, name=\'api_capture\'')
text = text.replace('views.api_real_last_capture, name=\'api_real_last_capture\'', 'views.api_last_capture, name=\'api_last_capture\'')

# Remove the old mock endpoints
lines = text.split('\n')
new_lines = []
skip = False
for line in lines:
    if 'api_preview' in line or 'api_save' in line or 'workbench_real' in line:
        continue
    if '# ── REAL 模式（新增）──' in line:
        continue
    new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

