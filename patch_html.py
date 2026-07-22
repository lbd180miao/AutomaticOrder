
import os
path = 'D:/workspace2/AutomaticOrder/templates/coordinates/workbench.html'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Make changes
text = text.replace('REAL 实机模式 · 坐标模块', '坐标模块')
text = text.replace('<link rel=\"stylesheet\" href=\"{% static \'coordinates/workbench_real.css\' %}\">', '')
text = text.replace('id=\"real-workbench\"', 'id=\"coordinate-workbench\"')
text = text.replace('api_capture_real', 'api_capture')
text = text.replace('api_real_last_capture', 'api_last_capture')
text = text.replace('data-mock-url=\"{% url \'coordinates:workbench\' %}\"', '')
text = text.replace('<span class=\"coordinate-kicker real-kicker\">📡 REAL MODE · 实机测试</span>', '<span class=\"coordinate-kicker real-kicker\">📡 坐标系设置与转换</span>')
text = text.replace('<h1>坐标模块 · REAL 实机模式</h1>', '<h1>坐标转换工作台</h1>')
text = text.replace('<a href=\"{% url \'coordinates:workbench\' %}\" class=\"btn btn-secondary\">← 返回 MOCK 模式</a>', '<a href=\"{% url \'vision:hand_eye_page\' %}\" class=\"btn btn-secondary\">手眼标定</a>')
text = text.replace('<span class=\"real-mode-badge\">🟢 REAL 实机模式</span>', '')
text = text.replace('class=\"coordinate-hero real-hero\"', 'class=\"coordinate-hero\"')
text = text.replace('class=\"coordinate-toolbar real-status-bar\"', 'class=\"coordinate-toolbar\"')
text = text.replace('class=\"coordinate-results real-results\"', 'class=\"coordinate-results\"')
text = text.replace('<span class=\"real-result-badge\">REAL MEASUREMENT</span>', '<span class=\"real-result-badge\">MEASUREMENT</span>')
text = text.replace('workbench_real.js', 'workbench.js')
text = text.replace('💡 从手眼标定结果中复制，或参考 MOCK 模式中的矩阵', '💡 从手眼标定结果中复制矩阵数据')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

