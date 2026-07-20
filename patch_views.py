import sys

file_path = "apps/vision/views.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target1 = '''            score=result['score'],'''
replace1 = '''            score=0.0,'''

if target1 in content:
    content = content.replace(target1, replace1)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done views.py")
else:
    print("Target not found")
