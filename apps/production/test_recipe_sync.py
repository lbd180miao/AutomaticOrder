# -*- coding: utf-8 -*-
"""sync_recipe_from_mes：REST 返回完整配方时 upsert；SOAP(20260801) 仅校验时回退本地配方。"""
from django.test import TestCase

from apps.production.models import Rack, RackRecipe
from apps.production.services import ProductionService


def _recipe(code, rack_type='T1', active=True):
    return RackRecipe.objects.create(
        recipe_code=code, name=f'配方{code}', rack_type=rack_type,
        layer_count=4, quantity_per_layer=6, total_quantity=24, is_active=active,
    )


class SyncRecipeFromMesTests(TestCase):
    def setUp(self):
        self.svc = ProductionService()
        self.rack = Rack.objects.create(rack_code='R1', rack_type='T1')

    def test_rest_full_recipe_upserts_and_assigns(self):
        resp = {'success': True, 'recipe': {
            'recipe_code': 'RCP-MES', 'name': 'MES配方', 'rack_type': 'T1',
            'layer_count': 3, 'quantity_per_layer': 8, 'total_quantity': 24,
            'layer_height': 120, 'layer_spacing': 150,
            'tolerance_x': 0, 'tolerance_y': 0, 'tolerance_z': 3,
        }}
        recipe = self.svc.sync_recipe_from_mes(self.rack, resp)
        self.assertEqual(recipe.recipe_code, 'RCP-MES')
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.current_recipe_id, recipe.pk)

    def test_soap_check_only_uses_unique_active_recipe(self):
        local = _recipe('RCP-LOCAL')
        resp = {'success': True, 'hu_qty': 26, 'hu_max_qty': 74, 'is_sealed': False}
        recipe = self.svc.sync_recipe_from_mes(self.rack, resp)
        self.assertEqual(recipe, local)
        self.rack.refresh_from_db()
        self.assertEqual(self.rack.current_recipe_id, local.pk)

    def test_soap_prefers_same_rack_type_when_multiple(self):
        _recipe('RCP-OTHER', rack_type='T2')
        match = _recipe('RCP-T1', rack_type='T1')
        resp = {'success': True}
        self.assertEqual(self.svc.sync_recipe_from_mes(self.rack, resp), match)

    def test_soap_ambiguous_returns_none(self):
        _recipe('RCP-A', rack_type='T9')
        _recipe('RCP-B', rack_type='T9')
        rack = Rack.objects.create(rack_code='R2')  # 无 rack_type，且全局有两个启用配方
        self.assertIsNone(self.svc.sync_recipe_from_mes(rack, {'success': True}))
        rack.refresh_from_db()
        self.assertIsNone(rack.current_recipe_id)

    def test_soap_keeps_existing_assignment(self):
        local = _recipe('RCP-KEEP')
        self.svc.assign_recipe_to_rack(self.rack, local)
        recipe = self.svc.sync_recipe_from_mes(self.rack, {'success': True})
        self.assertEqual(recipe, local)
