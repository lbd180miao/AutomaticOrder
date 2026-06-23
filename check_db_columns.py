"""
检查数据库中的实际列
"""
import sqlite3

db_path = 'db.sqlite3'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("检查 vision_racklocationresult 表的列结构：")
print("=" * 60)

cursor.execute("PRAGMA table_info(vision_racklocationresult)")
columns = cursor.fetchall()

for col in columns:
    cid, name, type_, notnull, default, pk = col
    print(f"  {name:30} {type_:15} {'NOT NULL' if notnull else ''}")

print("\n" + "=" * 60)
print(f"共 {len(columns)} 列")

# 检查是否缺少字段
required_fields = [
    'actual_x', 'actual_y', 'actual_z', 'offset_rz',
    'position_no', 'layer_no', 'confidence',
    'error_code', 'error_message', 'plc_write_status',
    'plc_error_message', 'raw_data_path', 'result_image_path', 'recipe_id'
]

existing_columns = [col[1] for col in columns]
missing = [field for field in required_fields if field not in existing_columns]

if missing:
    print(f"\n⚠ 缺少的字段: {', '.join(missing)}")
else:
    print("\n✓ 所有必需的字段都存在")

conn.close()
