from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import cv2
import numpy as np

from .algorithms.foam_geometry import register_product, geometry_config, ProductRegistrationError
from .algorithms.foam_inspector import _inspect_calibrated_sides, _inspect_layer_sides


class ProductRegistrationTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / 'reference.png')
        self.anchors = [[.05,.1,.25,.35], [.72,.1,.92,.35]]
        self.foams = {'left': [.3,.45,.45,.7], 'right': [.55,.45,.7,.7]}
        self.layer = [.25,.4,.75,.8]
        self.image = np.full((400,640,3), 25, np.uint8)
        rng = np.random.default_rng(123)
        for a,b,c,d in self.anchors:
            x,y,z,t = np.rint(np.array([a,b,c,d])*[640,400,640,400]).astype(int)
            texture = rng.integers(20,230,(t-y,z-x),np.uint8)
            texture = cv2.GaussianBlur(texture,(3,3),0)
            self.image[y:t,x:z] = texture[:,:,None]
        self.image[180:280,192:288] = 210
        self.image[180:280,352:448] = 210
        cv2.imwrite(self.path,self.image)
        self.cfg = geometry_config({'product_registration': {'enabled':True,'max_shift_px':25,
                                                            'max_rotation_deg':3}})['product_registration']

    def register(self,image):
        return register_product(image,self.path,self.anchors,list(self.foams.values()),self.cfg,self.layer)

    def test_product_translation_and_rotation_are_measured(self):
        matrix = cv2.getRotationMatrix2D((320,200),2,1)
        matrix[:,2] += [10,-4]
        current = cv2.warpAffine(self.image,matrix,(640,400))
        _,data = self.register(current)
        self.assertAlmostEqual(data['shift_x_px'],10,delta=1)
        self.assertAlmostEqual(data['shift_y_px'],-4,delta=1)
        self.assertAlmostEqual(data['rotation_deg'],-2,delta=.3)
        self.assertEqual(data['supported_anchors'],[0,1])

    def test_foam_only_movement_is_not_compensated(self):
        current = self.image.copy()
        current[180:280,192:288] = 25
        current[180:280,212:308] = 210
        _,data = self.register(current)
        self.assertAlmostEqual(data['shift_x_px'],0,delta=.1)
        self.assertAlmostEqual(data['shift_y_px'],0,delta=.1)

    def test_unobservable_or_single_anchor_never_passes(self):
        for current in (np.zeros_like(self.image), self.image.copy()):
            current[40:140,460:589] = 25
            with self.assertRaises(ProductRegistrationError):
                self.register(current)

    def test_inconsistent_anchor_motion_is_rejected(self):
        current = self.image.copy()
        current[40:140,32:160] = 25
        current[40:140,47:175] = self.image[40:140,32:160]
        with self.assertRaises(ProductRegistrationError):
            self.register(current)

    def test_pipeline_preserves_relative_foam_shift_and_invalid_status(self):
        standards = {}
        for side,x in (('left',192),('right',352)):
            mask=np.zeros((160,320),np.uint8)
            mask[20:120,x-160:x-160+96]=255
            standards[side]=mask
        cfg = dict(layer_search_roi=self.layer,standard_mask_space='layer-v3',
                   standard_masks=standards,product_registration=self.cfg,
                   product_reference_path=self.path,product_anchor_rois=self.anchors,
                   coverage_threshold=.75,max_offset_px=8)
        moved=self.image.copy();moved[180:280,192:288]=25;moved[180:280,212:308]=210
        current=cv2.warpAffine(moved,np.float32([[1,0,10],[0,1,4]]),(640,400))
        result,_,_,sides=_inspect_calibrated_sides(current,self.foams,0,cfg)
        self.assertEqual(result['coordinate_space'],'product_reference')
        self.assertFalse(result['is_passed'])
        self.assertAlmostEqual(sides['left']['offset_x_px'],20,delta=1)
        self.assertAlmostEqual(sides['right']['offset_x_px'],0,delta=1)
        result,*_=_inspect_calibrated_sides(np.zeros_like(current),self.foams,0,cfg)
        self.assertEqual(result['inspection_status'],'INVALID')
        self.assertFalse(result['is_passed'])


class FragmentMergeTests(TestCase):
    def scene(self):
        image=np.full((160,320,3),20,np.uint8)
        refs={'left':[30/320,50/160,110/320,110/160],
              'right':[200/320,50/160,280/320,110/160]}
        standards={}
        for side,x in (('left',30),('right',200)):
            image[50:110,x:x+80]=200
            mask=np.zeros((160,320),np.uint8);mask[50:110,x:x+80]=255
            standards[side]=mask
        cfg={'layer_search_roi':[0,0,1,1],'standard_mask_space':'layer-v3',
             'standard_masks':standards,'coverage_threshold':.75,'max_offset_px':10,
             'fragment_merge':{'enabled':True,'max_gap_px':8}}
        return image,refs,cfg

    def test_fragments_reunited_without_filling_missing_pixels(self):
        image,refs,cfg=self.scene();image[50:110,66:72]=20
        sides=_inspect_layer_sides(image,refs,cfg)
        self.assertEqual(sides['left']['fragment_count'],2)
        self.assertFalse(np.any(sides['left']['mask'][50:110,66:72]))
        self.assertAlmostEqual(sides['left']['coverage_ratio'],.925,delta=.01)
        self.assertFalse(np.any((sides['left']['mask']>0)&(sides['right']['mask']>0)))

    def test_far_or_different_color_parts_not_merged(self):
        image,refs,cfg=self.scene();image[50:110,55:85]=20
        self.assertEqual(_inspect_layer_sides(image,refs,cfg)['left']['fragment_count'],1)
        image,refs,cfg=self.scene();image[50:110,66:72]=20;image[50:110,72:110]=150
        cfg['fragment_merge']['max_color_distance']=10
        self.assertEqual(_inspect_layer_sides(image,refs,cfg)['left']['fragment_count'],1)

    def test_large_reflection_is_not_added_to_group(self):
        image,refs,cfg=self.scene();image[50:110,66:72]=20
        image[5:45,20:120]=200
        result=_inspect_layer_sides(image,refs,cfg)['left']
        self.assertFalse(np.any(result['mask'][:45]))

    def test_disabled_mode_preserves_single_component_behavior(self):
        image,refs,cfg=self.scene();image[50:110,66:72]=20
        cfg['fragment_merge']['enabled']=False
        result=_inspect_layer_sides(image,refs,cfg)['left']
        self.assertEqual(result['fragment_count'],1)
        self.assertFalse(result['is_complete'])
