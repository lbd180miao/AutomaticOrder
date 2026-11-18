import copy
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase

from . import rack_rivet
from .rack_robot_points import robot_point_difference
from .rack_cloud_service import evaluate_cloud


class RivetTests(SimpleTestCase):
    def setUp(self):
        self.cloud = np.zeros((60, 60, 3))
        self.image = np.zeros((60, 60), np.uint8)
        self.config = {'algorithm': 'rivet', 'rack_layers': 2, 'imageSize': [60, 60],
                       'rois': [dict(target=name, x=i*20, y=0, width=20, height=20)
                                for i, name in enumerate(rack_rivet.TARGETS)]}
        self.metadata = {'source': 'rvc_camera', 'camera': {'pointcloud_unit': 'mm', 'sn': 'test'}}
        self.xyz = np.array([[20., 10., 1000.], [20., 50., 1000.], [0., 30., 1000.]])
        self.context = {'T_flange_camera': np.eye(4).tolist(),
                        'T_base_flange': [[0,-1,0,100], [1,0,0,200], [0,0,1,300], [0,0,0,1]]}

    def measurement(self, xyz):
        return {'success': True, 'coordinateSystem': 'camera', 'unit': 'mm',
                'points': [dict(name=f'P{i+1}', xyz=p.tolist(), success=True) for i,p in enumerate(xyz)]}

    def detector(self, gray, roi, *args):
        return [dict(u=roi[0]+10., v=10., ranking_score=90., score=90.)], {}

    def test_unloading_preview_and_reference(self):
        self.config['rack_layout'] = 'unloading'
        self.config['rois'].pop(1)
        with patch.object(rack_rivet, 'detect_image', side_effect=self.detector), patch.object(
                rack_rivet, 'measure_with_fallback', side_effect=[
                    {'xyz_mm': self.xyz[i].tolist()} for i in (2, 0, 2)]):
            preview = rack_rivet.measure(self.cloud, self.image, self.config, self.metadata, preview_target='P3_rivet')
            self.assertEqual(preview['pixels'], [[50., 10.]])
            reference = rack_rivet.build_template(self.cloud, self.config, self.metadata, self.image)
        np.testing.assert_allclose(reference['relative_vectors'], [self.xyz[0]-self.xyz[2]])
        offsets = robot_point_difference(reference['measurement'], reference, self.context)['offsets']
        np.testing.assert_allclose(offsets, [[0, 0, 0]])

    def test_relative_delta_rotates_without_translation(self):
        reference = {'measurement': self.measurement(self.xyz)}
        moved = self.xyz + [100, 200, 300]
        moved[0] += [1, 2, 3]
        moved[1] += [-4, 5, -6]
        result = robot_point_difference(self.measurement(moved), reference, self.context)
        np.testing.assert_allclose(result['offsets'], [[-2, 1, 3], [-5, -4, -6]])
        fixed = robot_point_difference(self.measurement(self.xyz+[10,20,30]), reference, self.context)
        np.testing.assert_allclose(fixed['offsets'], np.zeros((2,3)))

    def test_template_detection_service_and_both_plc_groups(self):
        with patch.object(rack_rivet, 'detect_image', side_effect=self.detector), patch.object(
                rack_rivet, 'measure_with_fallback', side_effect=[{'xyz_mm': p.tolist(), 'status': 'OK_ESTIMATE'} for p in self.xyz]):
            reference = rack_rivet.build_template(self.cloud, self.config, self.metadata, self.image)
        np.testing.assert_allclose(reference['relative_vectors'], self.xyz[:2]-self.xyz[2])
        recipe = SimpleNamespace(roi_config={'cloud_center_config': self.config,
            'cloud_center_reference': reference}, max_offset_x=10, max_offset_y=10, max_offset_z=10, layer_count=2)
        moved = self.xyz.copy(); moved[0] += [1,2,3]; moved[1] += [-4,5,-6]
        with patch.object(rack_rivet, 'detect_image', side_effect=self.detector), patch.object(
                rack_rivet, 'measure_with_fallback', side_effect=[{'xyz_mm': p.tolist(), 'status': 'OK_ESTIMATE'} for p in moved]), patch(
                'apps.vision.rack_robot_points.workspace_context', return_value=self.context):
            result = evaluate_cloud(recipe, self.cloud, self.metadata, camera_image=self.image)
        self.assertTrue(result['plc_publish_allowed'], result['error_message'])
        from apps.devices.plc_position_debug import dual_group_position
        plc = dual_group_position(result, recipe)
        self.assertEqual([plc['compensation_'+a] for a in ('x','y','z','x2','y2','z2')], [-2,1,3,-5,-4,-6])
        recipe.max_offset_z = 2
        self.assertFalse(dual_group_position(result, recipe)['is_success'])
        with patch.object(rack_rivet, 'detect_image', return_value=([], {})):
            failed = evaluate_cloud(recipe, self.cloud, self.metadata, camera_image=self.image)
        self.assertFalse(failed['plc_publish_allowed'])
        self.assertEqual(failed['robot_groups'], {})

    def test_missing_ambiguous_or_bad_depth_rejects_template(self):
        for hits, measurement in [([], None),
                ([dict(u=10.,v=10.,ranking_score=90),dict(u=15.,v=10.,ranking_score=89)], None),
                ([dict(u=10.,v=10.,ranking_score=90)], {'xyz_mm': None, 'status': 'NO_DEPTH'})]:
            with self.subTest(hits=hits), patch.object(rack_rivet, 'detect_image', return_value=(hits, {})), patch.object(
                    rack_rivet, 'measure_with_fallback', return_value=measurement):
                with self.assertRaises(ValueError):
                    rack_rivet.build_template(self.cloud, self.config, self.metadata, self.image)

    def test_old_template_missing_image_and_changed_pose_rejected(self):
        with self.assertRaises(ValueError):
            rack_rivet.match_template(self.cloud, self.metadata, {'version':'cloud_match_v1'}, self.image)
        with self.assertRaises(ValueError):
            rack_rivet.measure(self.cloud, None, self.config, self.metadata)
        reference = {'measurement': self.measurement(self.xyz)}
        reference['measurement']['robot_transform_context'] = copy.deepcopy(self.context)
        reference['measurement']['robot_transform_context']['T_base_flange'] = np.eye(4).tolist()
        with self.assertRaises(ValueError):
            robot_point_difference(self.measurement(self.xyz), reference, self.context)


from django.test import TestCase, override_settings


@override_settings(MIDDLEWARE=[])
class RivetEndpointTests(TestCase):
    def test_save_reload_evaluate_and_history(self):
        import json
        import tempfile
        from pathlib import Path
        import cv2
        from django.urls import reverse
        from .models import RackLocationRecipe, RackLocationResult
        from .rack_location import result_payload, PlcVisionResultWriter
        fixture = RivetTests(); fixture.setUp()
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder), patch.object(
                rack_rivet, 'detect_image', side_effect=fixture.detector), patch.object(
                rack_rivet, 'measure_with_fallback', side_effect=[{'xyz_mm': p.tolist(), 'status': 'OK_ESTIMATE'}
                    for p in list(fixture.xyz)*2]), patch('apps.vision.rack_robot_points.workspace_context', return_value=fixture.context), patch(
                'apps.vision.rack_cloud_service.archive_history'):
            root = Path(folder)
            np.save(root/'frame.npy', fixture.cloud)
            cv2.imwrite(str(root/'frame_image2d.png'), fixture.image)
            (root/'frame.units.json').write_text(json.dumps({'unit':'mm', 'capture_metadata':fixture.metadata}))
            recipe = RackLocationRecipe.objects.create(recipe_name='rivet-test')
            base = {'recipe_id':recipe.pk, 'pointcloud_token':'frame.npy', 'algorithm':'rivet'}
            def post(name, body):
                return self.client.post(reverse('vision:rack_dual_point_'+name), json.dumps(body), content_type='application/json')
            prepared = post('prepare', base)
            self.assertEqual(prepared.status_code, 200, prepared.content)
            body = {**base, **{key:prepared.json()[key] for key in ('image_token','cloud_token')}, 'config':fixture.config}
            saved = post('cloud_match', {**body,'action':'save_template'})
            self.assertEqual(saved.status_code, 200, saved.content)
            self.assertEqual(post('prepare', base).status_code, 200)
            evaluated = post('cloud_match', body)
            self.assertEqual(evaluated.status_code, 200, evaluated.content)
            self.assertTrue(evaluated.json()['is_success'], evaluated.content)
            record = RackLocationResult.objects.get(pk=evaluated.json()['result_id'])
            self.assertEqual(PlcVisionResultWriter()._revalidate_offsets(record), '')
            history = result_payload(record)
            self.assertIsNone(history['compensation_matrix'])
            self.assertEqual(history['plc_payload']['compensation_z2'], 0)
