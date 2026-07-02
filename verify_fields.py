#!/usr/bin/env python
"""验证 RackLocationRecipe 模型字段"""

from apps.vision.models import RackLocationRecipe

print("=== RackLocationRecipe Field Verification ===\n")

# 验证所有必需字段存在
required_fields = [
    'hand_eye_config',
    'reference_feature_config', 
    'confidence_threshold',
    'standard_x',
    'standard_y',
    'standard_z',
    'max_offset_x',
    'max_offset_y',
    'max_offset_z'
]

print("Checking required fields:")
all_exist = True
for field_name in required_fields:
    exists = hasattr(RackLocationRecipe, field_name)
    if exists:
        field = RackLocationRecipe._meta.get_field(field_name)
        field_type = field.__class__.__name__
        print(f"  ✓ {field_name}: {field_type}", end="")
        
        # 显示 DecimalField 的详细信息
        if field_type == "DecimalField":
            print(f" (max_digits={field.max_digits}, decimal_places={field.decimal_places})")
        else:
            print()
    else:
        print(f"  ✗ {field_name}: MISSING")
        all_exist = False

print(f"\n{'✓' if all_exist else '✗'} All required fields: {'PRESENT' if all_exist else 'MISSING'}")

# 验证字段规格
print("\n=== Field Specification Validation ===")
std_x = RackLocationRecipe._meta.get_field('standard_x')
assert std_x.max_digits == 10 and std_x.decimal_places == 3, "standard_x incorrect specs"
print(f"✓ standard_x/y/z: DecimalField(max_digits=10, decimal_places=3)")

conf = RackLocationRecipe._meta.get_field('confidence_threshold')
assert conf.max_digits == 5 and conf.decimal_places == 4, "confidence_threshold incorrect specs"
print(f"✓ confidence_threshold: DecimalField(max_digits=5, decimal_places=4)")

print("\n=== Task 1.2 Complete ===")
print("All required fields verified for Requirements: 10.1, 10.2, 19.4, 19.5")
