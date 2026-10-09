import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.test import TestCase, SimpleTestCase, RequestFactory, override_settings
from . import rack_spatial as s
from .models import RackLocationRecipe, RackLocationResult
from .rack_spatial_service import teach, calculate, robot_group_results
from .rack_location import RackLocationService


def scene():
    rng = np.random.default_rng(71)
    x = np.linspace(-200,200,600)
    top = np.column_stack([x,rng.normal(0,.5,len(x)),1000+rng.normal(0,.5,len(x))])
    bottom = top + [0,300,0]
    pillar = np.column_stack([rng.normal(0,.5,len(x)),np.linspace(-40,340,len(x)),1000+rng.normal(0,.5,len(x))])
    cloud = np.concatenate([top,pillar,bottom]).reshape(30,60,3)
    rois = {name:dict(x=0,y=i*10,w=60,h=10) for i,name in enumerate(s.NAMES)}
    config = dict(spatial_rois=s.teach_boxes(cloud,rois,10))
    # Exclude member intersections from beam ROIs for a stable isolated regression fixture.
    return cloud,rois,config


class SpatialMathTests(SimpleTestCase):
    def test_axis_ratio_quality_warning_does_not_block_fitting(self):
        # Uniform ellipse: covariance eigenvalue ratio equals squared radius ratio.
        angles = np.linspace(0, 2*np.pi, 720, endpoint=False)
        for ratio, accepted in ((1.965, True), (1.6, True), (1.4, False), (1.0, False)):
            points = np.column_stack((100*np.sqrt(ratio)*np.cos(angles),
                                      100*np.sin(angles), np.full(len(angles), 1000)))
            with self.subTest(ratio=ratio):
                if accepted:
                    axis = s.fit_axis(points)
                    self.assertGreater(abs(axis['direction'][0]), .99)
                else:
                    axis = s.fit_axis(points)
                    self.assertTrue(axis['quality_warnings'])
                    self.assertTrue(np.isfinite(axis['direction']).all())

    def test_aabbs_enclose_every_valid_taught_point(self):
        cloud,rois,config=scene()
        for i,name in enumerate(s.NAMES):
            lo,hi=s.bounds(config['spatial_rois'][name])
            self.assertTrue(((cloud[i*10:(i+1)*10]>=lo)&(cloud[i*10:(i+1)*10]<=hi)).all())
        self.assertNotIn('local_template_rois',config)

    def test_spatial_extraction_ignores_pixel_order(self):
        cloud,_,config=scene()
        standard=s.compute(cloud,config)
        shuffled=cloud.reshape(-1,3)[np.random.default_rng(1).permutation(cloud.size//3)]
        result=s.compute(shuffled,config,standard)
        for group in result['groups'].values():
            np.testing.assert_allclose(group['delta_T'],np.eye(4),atol=1e-9)

    def test_independent_beam_motion(self):
        cloud,_,config=scene()
        standard=s.compute(cloud,config)
        changed=cloud.copy();changed[:10,:,1]-=4;changed[20:,:,1]+=6
        result=s.compute(changed,config,standard)
        self.assertLess(result['groups']['A']['translation_mm']['y'],-3)
        self.assertGreater(result['groups']['B']['translation_mm']['y'],5)

    def test_rigid_rotation_and_translation(self):
        from scipy.spatial.transform import Rotation
        cloud,_,config=scene()
        # Widen boxes to retain a moved member, while preserving region separation.
        for box in config['spatial_rois'].values():
            box['Zmin'] -= 30; box['Zmax'] += 30
        standard=s.compute(cloud,config)
        rotation=Rotation.from_euler('y',1,degrees=True).as_matrix()
        # Rotate about a point in the rack, not the camera origin.
        center=np.array([0,0,1000])
        moved=(cloud-center)@rotation.T+center+[0,0,2]
        result=s.compute(moved,config,standard)
        for group in result['groups'].values():
            self.assertAlmostEqual(group['rotation_deg']['ry'],1,delta=.03)
            np.testing.assert_allclose(np.array(group['delta_T'])[:3,:3],rotation,atol=.001)

    def test_invalid_empty_and_parallel_fail(self):
        cloud,_,config=scene()
        with self.assertRaises(ValueError): s.compute(np.zeros_like(cloud),config)
        axis=dict(point=[0,0,1000],direction=[1,0,0])
        with self.assertRaises(ValueError): s.pair_frame(axis,axis)
        with self.assertRaises(ValueError): s.bounds(dict(Xmin=2,Xmax=1,Ymin=0,Ymax=1,Zmin=0,Zmax=1))

    def test_projection_recovers_eight_corners(self):
        y,x=np.indices((40,60)); z=1000+2*x+y
        cloud=np.stack([(x-30)*z/500,(y-20)*z/510,z],axis=-1)
        model=s.projection_model(cloud)
        pixels=s.project(cloud[::10,::10].reshape(-1,3),model)
        np.testing.assert_allclose(pixels,np.column_stack([x[::10,::10].ravel(),y[::10,::10].ravel()]),atol=1e-8)


class SpatialTeachingTests(TestCase):
    def setUp(self):
        self.factory=RequestFactory()
        self.recipe=RackLocationRecipe.objects.create(recipe_name='Spatial regression',roi_config={'target_roi':{'x':1}})
        self.cloud,self.rois,self.config=scene()

    def post(self,data):
        return teach(self.factory.post('/spatial-teach/',data=json.dumps(data),content_type='application/json'))

    def test_preview_save_reload_and_detect_without_pixels(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root, override_settings(MEDIA_ROOT=root):
            with patch.object(RackLocationService,'_load_workbench_pointcloud',return_value=self.cloud):
                preview=self.post(dict(recipe_id=self.recipe.pk,pointcloud_token='same-frame.npy',local_template_rois=self.rois,margin_mm=10))
                self.assertEqual(preview.status_code,200,preview.content)
                data=json.loads(preview.content)
                self.recipe.refresh_from_db();self.assertIn('target_roi',self.recipe.roi_config)
                saved=self.post(dict(action='save',recipe_id=self.recipe.pk,candidate=data['candidate']))
                self.assertEqual(saved.status_code,200,saved.content)
                self.recipe.refresh_from_db()
                self.assertEqual(self.recipe.roi_config['target_roi'], {'x': 1})
                self.assertEqual(self.recipe.roi_config['local_template_rois'], self.rois)
                path=Path(root)/'vision'/'rack_recipes'/str(self.recipe.pk)/'roi_config.json'
                self.assertIn('standard_axes',json.loads(path.read_text(encoding='utf-8')))
                context = {'T_base_flange': {'matrix': np.eye(4).tolist()}, 'T_flange_camera': {'matrix': np.eye(4).tolist()}}
                with patch.object(RackLocationService, '_recipe_transform_context', return_value=context):
                    result=calculate(RackLocationService(),token='same-frame.npy',recipe=self.recipe,save_record=True)
                self.assertEqual(set(result['groups']),{'A','B'})
                repeated=calculate(RackLocationService(),token='same-frame.npy',recipe=self.recipe)
                for name in ('A', 'B'):
                    np.testing.assert_allclose(repeated['groups'][name]['delta_T'],result['groups'][name]['delta_T'])
                record=RackLocationResult.objects.get(pk=result['result_id'])
                self.assertEqual(record.result_data['algorithm_version'],s.VERSION)
                self.assertFalse(record.result_data['plc_payload']['compensation_valid'])
                self.assertEqual(set(record.result_data['robot_groups']), {'A', 'B'})
                self.assertEqual(record.result_data['transform_context'], context)
                service=RackLocationService()
                stored=service.save_workbench_result(token='same-frame.npy',roi_config={},recipe_id=self.recipe.pk)
                self.assertIsInstance(stored,RackLocationResult)
                with patch('apps.vision.rack_spatial_service.calculate', return_value={'groups': {}}) as compute:
                    service.calculate_workbench(token='same-frame.npy',roi_config={'local_template_rois': {'broken': True}},recipe_id=self.recipe.pk)
                    self.assertTrue(compute.called)

    def test_save_preserves_editor_positions_without_changing_spatial_computation(self):
        editor = {'target_roi': {'x': 2, 'y': 3, 'w': 40, 'h': 20},
                  'layer_spacing_line': {'start': {'x': 4, 'y': 5}, 'end': {'x': 4, 'y': 20}}}
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            with patch.object(RackLocationService, '_load_workbench_pointcloud', return_value=self.cloud):
                response = self.post(dict(recipe_id=self.recipe.pk, pointcloud_token='same-frame.npy',
                                         local_template_rois=self.rois, roi_config=editor, margin_mm=10))
                self.assertEqual(response.status_code, 200, response.content)
                saved = self.post(dict(action='save', recipe_id=self.recipe.pk,
                                       candidate=json.loads(response.content)['candidate']))
                self.assertEqual(saved.status_code, 200, saved.content)
                self.recipe.refresh_from_db()
                for key, value in editor.items():
                    self.assertEqual(self.recipe.roi_config[key], value)
                first = calculate(RackLocationService(), token='same-frame.npy', recipe=self.recipe)
                self.recipe.roi_config['target_roi'] = None
                self.recipe.roi_config['local_template_rois'] = {'broken': True}
                second = calculate(RackLocationService(), token='same-frame.npy', recipe=self.recipe)
                for name in ('A', 'B'):
                    np.testing.assert_allclose(first['groups'][name]['delta_T'], second['groups'][name]['delta_T'])

    def test_quality_warning_is_persisted_while_both_groups_are_computed(self):
        self.recipe.roi_config = self.config
        self.recipe.local_template_std = s.compute(self.cloud, self.config)
        self.recipe.save()
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root), patch.object(s, 'MIN_AXIS_VARIANCE_RATIO', 1e9):
            result = calculate(RackLocationService(), token='warning-frame.npy', recipe=self.recipe,
                               cloud=self.cloud, save_record=True)
        self.assertTrue(result['locate_ok'])
        self.assertEqual(set(result['groups']), {'A', 'B'})
        self.assertTrue(result['quality_warnings'])
        self.assertIn('当前帧', result['warning_message'])
        saved = RackLocationResult.objects.get(pk=result['result_id'])
        self.assertEqual(saved.result_data['quality_warnings'], result['quality_warnings'])
        self.assertEqual(saved.result_data['warning_message'], result['warning_message'])

    def test_tampered_candidate_rejected(self):
        response=self.post(dict(action='save',recipe_id=self.recipe.pk,candidate='fake'))
        self.assertEqual(response.status_code,400)


class RobotGroupConversionTests(SimpleTestCase):
    def test_two_groups_use_full_hand_eye_transform(self):
        from scipy.spatial.transform import Rotation
        base = np.eye(4)
        base[:3, :3] = Rotation.from_euler('z', 90, degrees=True).as_matrix()
        base[:3, 3] = [100, 200, 300]
        hand = np.eye(4)
        hand[:3, 3] = [20, 30, 40]
        context = {'T_base_flange': {'matrix': base.tolist()},
                   'T_flange_camera': {'matrix': hand.tolist()}}
        a = np.eye(4); a[:3, 3] = [5, 0, 0]
        b = np.eye(4); b[:3, :3] = Rotation.from_euler('x', 3, degrees=True).as_matrix()
        b[:3, 3] = [0, -7, 2]
        service = RackLocationService()
        with patch.object(service, '_recipe_transform_context', return_value=context) as snapshot:
            result = robot_group_results(service, None, {'A': {'delta_T': a.tolist()}, 'B': {'delta_T': b.tolist()}})
        snapshot.assert_called_once()
        self.assertEqual(result['robot_conversion_error'], '')
        np.testing.assert_allclose(list(result['robot_groups']['A']['translation_mm'].values()), [0, 5, 0], atol=1e-10)
        expected = (base @ hand) @ b @ np.linalg.inv(base @ hand)
        np.testing.assert_allclose(result['robot_groups']['B']['matrix'], expected, atol=1e-10)
        self.assertEqual(result['transform_context'], context)

    def test_missing_or_invalid_calibration_does_not_fabricate_robot_values(self):
        service = RackLocationService()
        for context in ({}, {'T_base_flange': {'matrix': np.zeros((4,4)).tolist()},
                              'T_flange_camera': {'matrix': np.eye(4).tolist()}}):
            with self.subTest(context=context), patch.object(service, '_recipe_transform_context', return_value=context):
                result = robot_group_results(service, None, {'A': {'delta_T': np.eye(4).tolist()}, 'B': {'delta_T': np.eye(4).tolist()}})
                self.assertEqual(result['robot_groups'], {})
                self.assertTrue(result['robot_conversion_error'])


class LegacyRobotGroupsTests(SimpleTestCase):
    def test_saved_reference_produces_two_independent_robot_deltas(self):
        from types import SimpleNamespace
        from .rack_spatial_service import legacy_robot_groups
        cloud, rois, _ = scene()
        moved = cloud.copy()
        moved[:10, :, 1] -= 4
        moved[20:, :, 1] += 6
        recipe = SimpleNamespace(pk=8, roi_config={}, local_template_std={'source_result_id': 293})
        record = SimpleNamespace(pk=293, recipe_id=8, raw_data_path='standard.npy', result_data={'local_template_rois': rois})
        context = {'T_base_flange': {'matrix': np.eye(4).tolist()}, 'T_flange_camera': {'matrix': np.eye(4).tolist()}}
        service = RackLocationService()
        with patch('apps.vision.rack_spatial_service.RackLocationResult.objects.get', return_value=record), patch.object(service, '_load_workbench_pointcloud', return_value=cloud), patch.object(service, '_recipe_transform_context', return_value=context):
            result = legacy_robot_groups(service, recipe, moved, rois)
        self.assertEqual(result['robot_conversion_error'], '')
        self.assertLess(result['robot_groups']['A']['pose6d']['y'], -3)
        self.assertGreater(result['robot_groups']['B']['pose6d']['y'], 5)
        self.assertEqual(result['robot_groups_reference_result_id'], 293)


    def test_failure_identifies_reference_or_current_frame_and_roi(self):
        from types import SimpleNamespace
        from .rack_spatial_service import legacy_robot_groups
        cloud, rois, _ = scene()
        recipe = SimpleNamespace(pk=8, roi_config={}, local_template_std={'source_result_id': 293})
        record = SimpleNamespace(pk=293, recipe_id=8, raw_data_path='standard.npy', result_data={'local_template_rois': rois})
        service = RackLocationService()
        real_fit = s.fit_axis
        for failed_call, frame, region in ((1, '标准帧（记录 #293）', 'Π2（橙框）'), (5, '当前帧', 'Π3（粉框）')):
            calls = []
            def fit(points, voxel):
                index = len(calls)
                calls.append(index)
                if index == failed_call:
                    raise ValueError('构件主轴不明确')
                return real_fit(points, voxel)
            with self.subTest(frame=frame), patch('apps.vision.rack_spatial_service.RackLocationResult.objects.get', return_value=record), patch.object(service, '_load_workbench_pointcloud', return_value=cloud), patch.object(s, 'fit_axis', side_effect=fit):
                result = legacy_robot_groups(service, recipe, cloud, rois)
            self.assertEqual(result['robot_groups'], {})
            self.assertIn(frame, result['robot_conversion_error'])
            self.assertIn(region, result['robot_conversion_error'])
            self.assertIn('构件主轴不明确', result['robot_conversion_error'])

    def test_spatial_preview_and_calculation_label_the_frame(self):
        cloud, _, config = scene()
        standard = s.compute(cloud, config)
        for reference, label in ((None, '标准帧（示教预览）'), (standard, '当前帧')):
            with self.subTest(label=label), patch.object(s, 'fit_axis', side_effect=ValueError('构件主轴不明确')):
                with self.assertRaisesRegex(ValueError, label.replace('（', '.').replace('）', '.') + '.*Π1'):
                    s.compute(cloud, config, reference)


class LegacyStandardSaveTests(TestCase):
    def test_save_freezes_new_axes_and_rejects_bad_standard_without_overwriting(self):
        from .views import api_rack_location_calibrate_standard
        from .rack_spatial_service import legacy_robot_groups
        from types import SimpleNamespace
        cloud, rois, _ = scene()
        recipe = RackLocationRecipe.objects.create(recipe_name='standard-save', local_template_std={'source_result_id': 268})
        record = SimpleNamespace(pk=500, id=500, recipe_id=recipe.pk, raw_data_path='standard.npy',
                                 result_data={'local_template_cur': {'T': np.eye(4).tolist()}, 'local_template_rois': rois})
        factory = RequestFactory()
        def save():
            return api_rack_location_calibrate_standard(factory.post('/standard/', data=json.dumps({'result_id':500}), content_type='application/json'), recipe.pk)
        with patch('apps.vision.views.RackLocationResult.objects.get', return_value=record), patch('apps.vision.views.LocalFrameResult.from_dict'), patch('apps.vision.views.RackStructureValidator') as validator:
            validator.return_value.validate.return_value.to_dict.return_value = {}
            with patch('apps.vision.rack_spatial_service.reference_axes_from_record', side_effect=ValueError('标准帧 Π3 无效')):
                self.assertEqual(save().status_code, 400)
            recipe.refresh_from_db()
            self.assertEqual(recipe.local_template_std['source_result_id'], 268)
            with patch.object(RackLocationService, '_load_workbench_pointcloud', return_value=cloud):
                response = save()
            self.assertEqual(response.status_code, 200, response.content)
        recipe.refresh_from_db()
        self.assertEqual(recipe.local_template_std['dual_axis_standard']['source_result_id'], 500)
        context = {'T_base_flange': {'matrix': np.eye(4).tolist()}, 'T_flange_camera': {'matrix': np.eye(4).tolist()}}
        with patch('apps.vision.rack_spatial_service.RackLocationResult.objects.get', side_effect=AssertionError('must not reload old frame')), patch.object(RackLocationService, '_recipe_transform_context', return_value=context):
            result = legacy_robot_groups(RackLocationService(), recipe, cloud, rois)
        self.assertEqual(result['robot_conversion_error'], '')
        self.assertEqual(result['robot_groups_reference_result_id'], 500)
