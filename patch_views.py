
import os
path = 'D:/workspace2/AutomaticOrder/apps/coordinates/views.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Remove api_preview and api_save
import re
text = re.sub(r'@require_POST\s+def api_preview\(request\):.*?(?=@require_POST)', '', text, flags=re.DOTALL)
text = re.sub(r'@require_POST\s+def api_save\(request\):.*?(?=@require_POST)', '', text, flags=re.DOTALL)

# Remove workbench_real
text = re.sub(r'def workbench_real\(request\):.*?(?=@require_POST)', '', text, flags=re.DOTALL)

# Rename api_capture_real and api_real_last_capture
text = text.replace('api_capture_real', 'api_capture')
text = text.replace('api_real_last_capture', 'api_last_capture')

# Also remove the # REAL 模式 headers
text = re.sub(r'# ───+\n# REAL 模式（以下为新增，不影响上方任何已有接口）\n# ───+\n', '', text)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

