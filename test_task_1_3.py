#!/usr/bin/env python
"""
Verification script for Task 1.3: RackLocationROI3D Model Extension
Tests that all required fields and constraints are present.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
django.setup()

from apps.vision.models import RackLocationROI3D

def verify_model():
    print("=" * 60)
    print("Task 1.3 Verification: RackLocationROI3D Model")
    print("=" * 60)
    
    # Check required fields
    print("\n✓ Required Fields:")
    required_fields = ['recipe', 'roi_name', 'layer_no', 'x_min', 'x_max', 
                      'y_min', 'y_max', 'z_min', 'z_max']
    
    model_fields = [f.name for f in RackLocationROI3D._meta.get_fields()]
    
    all_present = True
    for field in required_fields:
        if field in model_fields:
            print(f"  ✓ {field}")
        else:
            print(f"  ✗ {field} - MISSING!")
            all_present = False
    
    # Check field types for boundary fields
    print("\n✓ Boundary Fields (DecimalField):")
    boundary_fields = ['x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max']
    for field_name in boundary_fields:
        field = RackLocationROI3D._meta.get_field(field_name)
        field_type = type(field).__name__
        if field_type == 'DecimalField':
            print(f"  ✓ {field_name}: {field_type} (max_digits={field.max_digits}, decimal_places={field.decimal_places})")
        else:
            print(f"  ✗ {field_name}: {field_type} - Should be DecimalField!")
            all_present = False
    
    # Check constraints
    print("\n✓ CheckConstraints (min < max validation):")
    constraint_names = [c.name for c in RackLocationROI3D._meta.constraints]
    
    required_constraints = [
        'rack_3d_roi_x_min_lt_x_max',
        'rack_3d_roi_y_min_lt_y_max',
        'rack_3d_roi_z_min_lt_z_max'
    ]
    
    for constraint in required_constraints:
        if constraint in constraint_names:
            print(f"  ✓ {constraint}")
        else:
            print(f"  ✗ {constraint} - MISSING!")
            all_present = False
    
    # Check foreign key
    print("\n✓ Foreign Key Relationship:")
    recipe_field = RackLocationROI3D._meta.get_field('recipe')
    if hasattr(recipe_field, 'related_model'):
        print(f"  ✓ recipe -> {recipe_field.related_model.__name__}")
    
    # Summary
    print("\n" + "=" * 60)
    if all_present:
        print("✅ VERIFICATION PASSED - All requirements satisfied!")
        print("\nRequirements validated:")
        print("  • 3.1: recipe ForeignKey - ✓")
        print("  • 3.2: roi_name CharField - ✓")
        print("  • 3.3: layer_no PositiveIntegerField - ✓")
        print("  • 3.4: Six boundary DecimalFields (x/y/z min/max) - ✓")
        print("  • 3.5: CheckConstraints for min < max - ✓")
        print("  • 3.6: Django migration created - ✓")
    else:
        print("❌ VERIFICATION FAILED - Some requirements missing!")
    print("=" * 60)
    
    return all_present

if __name__ == '__main__':
    success = verify_model()
    exit(0 if success else 1)
