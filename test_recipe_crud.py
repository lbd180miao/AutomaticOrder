"""
测试视觉配方的增删改查功能
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_create_recipe():
    """测试创建配方"""
    print("\n=== 测试创建配方 ===")
    url = f"{BASE_URL}/vision/api/recipes/foam-2d/create/"
    data = {
        "name": "测试配方 - POS 5",
        "pos": 5,
        "remark": "这是一个测试配方"
    }
    
    response = requests.post(url, json=data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
    return response.json()

def test_get_recipes():
    """测试获取配方列表"""
    print("\n=== 测试获取配方列表 ===")
    url = f"{BASE_URL}/vision/api/recipes/?recipe_type=FOAM_2D&is_active=true"
    
    response = requests.get(url)
    print(f"状态码: {response.status_code}")
    result = response.json()
    print(f"配方数量: {len(result.get('recipes', []))}")
    for recipe in result.get('recipes', []):
        print(f"  - POS {recipe['pos']}: {recipe['name']}")
    return result

def test_update_recipe(recipe_id):
    """测试更新配方"""
    print(f"\n=== 测试更新配方 ID={recipe_id} ===")
    url = f"{BASE_URL}/vision/api/recipes/foam-2d/save/"
    data = {
        "id": recipe_id,
        "pos": 5,
        "name": "测试配方 - POS 5 (已更新)",
        "camera_side": "both",
        "image_width": 1280,
        "image_height": 720,
        "roi_config": {
            "leftFoamROI": {"x": 200, "y": 150, "width": 100, "height": 80},
            "rightFoamROI": {"x": 800, "y": 150, "width": 100, "height": 80}
        },
        "threshold_config": {
            "coverage_threshold": 0.8,
            "score_threshold": 0.85,
            "max_offset_px": 25
        },
        "is_active": True,
        "remark": "配方已更新"
    }
    
    response = requests.post(url, json=data)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
    return response.json()

def test_delete_recipe(recipe_id):
    """测试删除配方"""
    print(f"\n=== 测试删除配方 ID={recipe_id} ===")
    url = f"{BASE_URL}/vision/api/recipes/foam-2d/{recipe_id}/delete/"
    
    response = requests.post(url)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
    return response.json()

if __name__ == "__main__":
    print("=" * 60)
    print("视觉配方 CRUD 功能测试")
    print("=" * 60)
    
    # 1. 创建配方
    create_result = test_create_recipe()
    if create_result.get('success'):
        recipe_id = create_result['recipe']['id']
        print(f"\n✓ 配方创建成功，ID: {recipe_id}")
        
        # 2. 获取配方列表
        test_get_recipes()
        
        # 3. 更新配方
        update_result = test_update_recipe(recipe_id)
        if update_result.get('success'):
            print(f"\n✓ 配方更新成功")
        
        # 4. 删除配方
        delete_result = test_delete_recipe(recipe_id)
        if delete_result.get('success'):
            print(f"\n✓ 配方删除成功")
        
        # 5. 再次获取配方列表确认删除
        print("\n=== 删除后的配方列表 ===")
        test_get_recipes()
    else:
        print(f"\n✗ 配方创建失败: {create_result.get('error')}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
