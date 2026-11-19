import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np
from django.test import SimpleTestCase, override_settings

from .algorithms.foam_stream import TemporalDecision, FoamStreamInspector, NORMAL, FALLEN, UNKNOWN


class TemporalTests(SimpleTestCase):
    def test_high_fps_confirms_and_latest_result_replaces_ng(self):
        detector = TemporalDecision(['left','right'])
        for i in range(12):
            result = detector.update(i/30, {'left':FALLEN,'right':NORMAL})
        self.assertEqual(result['state'],FALLEN)
        self.assertEqual(result['sides']['right']['state'],NORMAL)
        self.assertAlmostEqual(result['first_ng']['left'],.3)
        self.assertEqual(detector.update(.5,{})['state'],UNKNOWN)
        for t in [.6,.8,1.0]:
            result = detector.update(t, {'left':NORMAL,'right':NORMAL})
        self.assertEqual(result['state'], NORMAL)
        self.assertAlmostEqual(result['first_ng']['left'], .3)
        detector.reset()
        self.assertEqual(detector.update(0,{})['state'],UNKNOWN)

    def test_gap_invalid_and_duplicate_break_confirmation(self):
        detector = TemporalDecision(['left'])
        detector.update(0,{'left':FALLEN})
        detector.update(.2,{'left':FALLEN})
        self.assertEqual(detector.update(.4,{})['state'],UNKNOWN)
        self.assertEqual(detector.update(2,{'left':FALLEN})['state'],UNKNOWN)
        with self.assertRaises(ValueError):
            detector.update(2,{'left':FALLEN})

    def test_right_side_alone_causes_ng(self):
        detector = TemporalDecision(['left','right'])
        for t in [0,.2,.4]:
            result=detector.update(t,{'left':NORMAL,'right':FALLEN})
        self.assertEqual(result['state'],FALLEN)
        self.assertEqual(set(result['first_ng']),{'right'})


class SegmentationTests(SimpleTestCase):
    def test_darkness_not_fallen_and_backing_exposure_is_fallen(self):
        detector=object.__new__(FoamStreamInspector)
        detector.config={}
        standard=np.full((100,100),100,dtype=np.float32)
        valid=np.ones((100,100),bool)
        self.assertEqual(detector._measure(standard,standard,valid)['observation'],NORMAL)
        self.assertEqual(detector._measure(np.zeros_like(standard),standard,valid)['observation'],UNKNOWN)
        folded=standard.copy();folded[:40]=200
        self.assertEqual(detector._measure(folded,standard,valid)['observation'],FALLEN)
        valid[:40]=False
        self.assertEqual(detector._measure(folded,standard,valid)['observation'],UNKNOWN)


class VideoAPITests(SimpleTestCase):
    def test_workbench_and_post_only_endpoints(self):
        response=self.client.get('/vision/foam-inspector/')
        self.assertContains(response,'导入视频')
        self.assertEqual(self.client.get('/vision/api/foam/stream/video/').status_code,405)
        response=self.client.post('/vision/api/foam/stream/video/',data=json.dumps({'sample':'../db.sqlite3'}),content_type='application/json')
        self.assertEqual(response.status_code,400)

    def test_debug_video_decodes_and_seek_resets_without_plc(self):
        from .foam_video_sessions import VideoSession
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'clip.avi'
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,48))
            for _ in range(5):writer.write(np.full((48,64,3),80,np.uint8))
            writer.release()
            fake=Mock()
            fake.process.side_effect=lambda frame, timestamp, frame_id:dict(
                state=UNKNOWN,sides={},timestamp=timestamp,frame_id=frame_id,elapsed_ms=1)
            with patch('apps.vision.foam_video_sessions.FoamStreamInspector',return_value=fake), \
                 patch('apps.devices.adapters.plc.PLCAdapter.write_point',side_effect=AssertionError('debug must not write')):
                session=VideoSession(path)
                try:
                    self.assertFalse(session.next()['plc_enabled'])
                    self.assertEqual(session.next(seek=3)['result']['frame_id'],3)
                    fake.reset.assert_called_once()
                    session.next()
                    self.assertTrue(session.next()['ended'])
                finally:session.close()

    @override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
    def test_upload_api_session_isolation_and_close(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import Client
        from . import foam_video_sessions as sessions
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            source=Path(directory)/'source.avi'
            writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),6,(64,48))
            for _ in range(3):writer.write(np.full((48,64,3),100,np.uint8))
            writer.release()
            fake=Mock()
            fake.process.side_effect=lambda frame,timestamp,frame_id:dict(
                state=UNKNOWN,sides={},timestamp=timestamp,frame_id=frame_id,elapsed_ms=1)
            with patch('apps.vision.foam_video_sessions.FoamStreamInspector',return_value=fake):
                response=self.client.post('/vision/api/foam/stream/video/',{
                    'video':SimpleUploadedFile('user.avi',source.read_bytes(),'video/x-msvideo')})
                self.assertEqual(response.status_code,200,response.content)
                token=response.json()['session']
                try:
                    path=f'/vision/api/foam/stream/video/{token}/frame/'
                    self.assertEqual(Client().post(path,data='{}',content_type='application/json').status_code,400)
                    data=self.client.post(path,data='{}',content_type='application/json').json()
                    self.assertTrue(data['success'])
                    self.assertFalse(data['plc_enabled'])
                    self.assertTrue(data['image'].startswith('data:image/jpeg;base64,'))
                    self.client.post(f'/vision/api/foam/stream/video/{token}/close/')
                    self.assertNotIn(token,sessions._sessions)
                    self.assertEqual(list((Path(directory)/'vision/foam_video_debug').iterdir()),[])
                finally:
                    if token in sessions._sessions:
                        sessions._sessions.pop(token).close()


class LiveIntegrationTests(SimpleTestCase):
    def test_status_card_is_empty_and_details_collapsed_without_camera(self):
        from django.template.loader import render_to_string
        html=render_to_string('devices/foam_live_card.html')
        self.assertIn('暂无检测数据',html)
        self.assertIn('data-foam="details">',html)
        self.assertNotIn('data-foam="details" open',html)
        self.assertIn('<summary>查看详情</summary>',html)
        self.assertIn('data-foam="verdict" hidden',html)

    def test_camera_paths_are_json_serializable(self):
        from apps.devices.adapters.camera import CameraAdapter
        with tempfile.TemporaryDirectory() as directory, override_settings(
            MEDIA_ROOT=directory, AUTOMATIC_ORDER={'HIK_CAMERA':{
                'FEATURE_FILE':Path(directory)/'camera.mfs','SDK_LIB_DIR':Path(directory)}}):
            def capture(command,payload,result_path):
                json.dumps(payload)
                self.assertIsInstance(payload['feature_file'],str)
                self.assertIsInstance(payload['sdk_lib_dir'],str)
                return {'data':b''}
            with patch.object(CameraAdapter,'_persistent_capture',side_effect=capture):
                CameraAdapter().acquire_frame('test','FOAM_INSPECTION',continuous=True)

    def test_live_ng_workflow_never_writes_plc(self):
        from apps.workflow.station_service import StationWorkflowService
        service=object.__new__(StationWorkflowService)
        service._accept=Mock(return_value={'passed':False})
        service.vision=SimpleNamespace(simulated=False)
        service._write=Mock(side_effect=AssertionError('foam must not write PLC'))
        service._set_phase=Mock()
        service._channel_failure=Mock()
        cycle=SimpleNamespace(save=Mock())
        self.assertFalse(service._foam_trigger(cycle,{'foam_trigger':True}))
        service._accept.assert_not_called()
        cycle.save.assert_not_called()
        service._write.assert_not_called()

    def test_continuous_owner_rejects_single_capture(self):
        from apps.devices.adapters.camera import CameraAdapter
        with patch.object(CameraAdapter,'_stream_active',True):
            with self.assertRaisesRegex(RuntimeError,'连续检测'):
                CameraAdapter().capture('test','FOAM_INSPECTION')

    @override_settings(FOAM_STREAM_AUTO_START=False)
    def test_external_role_does_not_start_camera(self):
        from .foam_live import start_automatic
        with patch('apps.vision.foam_live.runtime.start') as start:
            start_automatic()
            start.assert_not_called()

    @override_settings(FOAM_STREAM_AUTO_START=True)
    def test_automatic_camera_start_does_not_require_plc(self):
        from .foam_live import start_automatic
        with patch('apps.vision.foam_live.runtime.start') as start:
            start_automatic()
            start.assert_called_once()

    def test_foam_bit_is_reserved_and_not_in_snapshot(self):
        from apps.devices.adapters.plc import PLCAdapter, MemoryPLCTransport
        from apps.devices.plc_db100 import POINTS_BY_NAME
        plc=PLCAdapter(MemoryPLCTransport())
        plc.transport.buffer[68]=16
        self.assertNotIn('foam_trigger',plc.read_listener_snapshot())
        self.assertEqual(POINTS_BY_NAME['layer_delta_z2'].offset,96)

    def test_capture_restart_resets_and_never_writes_plc(self):
        import time
        from .foam_live import LiveFoamRuntime
        from apps.devices.adapters.camera import CameraAdapter
        live=LiveFoamRuntime()
        fake=Mock()
        fake.process.side_effect=lambda frame,timestamp,frame_id:dict(
            state=NORMAL,sides={},timestamp=timestamp,frame_id=frame_id,elapsed_ms=1)
        def capture(*args,**kwargs):
            time.sleep(.02)
            self.assertTrue(kwargs['continuous'])
            return {}
        with patch('apps.vision.foam_live.FoamStreamInspector',return_value=fake), \
             patch.object(CameraAdapter,'acquire_frame',side_effect=capture), \
             patch.object(CameraAdapter,'decode_frame',return_value=np.full((48,64),100,np.uint8)), \
             patch.object(CameraAdapter,'close_worker'), \
             patch('apps.devices.adapters.plc.PLCAdapter.write_point',side_effect=AssertionError('no PLC writes')):
            try:
                live.start()
                deadline=time.monotonic()+2
                while not live.status()['result'] and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(live.status()['running'])
                self.assertEqual(live.status()['result']['state'],NORMAL)
                generation=live.status()['generation']
                live.reset()
                self.assertGreater(live.status()['generation'],generation)
                self.assertIsNone(live.status()['result'])
            finally:live.stop()
            self.assertFalse(CameraAdapter._stream_active)


class ManualContinuousTests(SimpleTestCase):
    def test_manual_pause_survives_new_runtime_and_resume_keeps_capture(self):
        from .foam_live import LiveFoamRuntime
        from apps.devices.plc_position_debug import ownership, active
        from apps.workflow.station_service import StationWorkflowService
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=directory):
            live=LiveFoamRuntime()
            service=object.__new__(StationWorkflowService)
            service.active_cycle=Mock(return_value=None)
            service._poll_once_owned=Mock(return_value=(None,True))
            with patch.object(live,'start'), patch.object(live,'stop') as stop:
                live.set_manual(True)
                self.assertTrue(LiveFoamRuntime().manual_status())
                self.assertEqual(service.poll_once(),(None,False))
                service._poll_once_owned.assert_not_called()
                with self.assertRaisesRegex(ValueError,'2D'):
                    with ownership('position'):
                        pass
                live.set_manual(False)
                self.assertFalse(live.manual_status())
                self.assertEqual(service.poll_once(),(None,True))
                stop.assert_not_called()
                with ownership() as (state,save):
                    self.assertFalse(active(state))

    def test_failed_start_does_not_pause_automatic(self):
        from .foam_live import LiveFoamRuntime
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=directory):
            live=LiveFoamRuntime()
            with patch.object(live,'start',side_effect=RuntimeError('camera unavailable')):
                with self.assertRaises(RuntimeError):live.set_manual(True)
            self.assertFalse(live.manual_status())

    def test_live_preview_updates_while_inference_is_busy(self):
        import threading
        import time
        from .foam_live import LiveFoamRuntime
        from apps.devices.adapters.camera import CameraAdapter
        release=threading.Event()
        entered=threading.Event()
        detector=Mock()
        def detect(frame, timestamp, frame_id):
            entered.set()
            release.wait(3)
            return dict(state=NORMAL,sides={},timestamp=timestamp,frame_id=frame_id,elapsed_ms=1)
        detector.process.side_effect=detect
        counter=[0]
        def capture(*args,**kwargs):
            time.sleep(.02)
            counter[0]+=1
            return np.full((48,64),counter[0]%255,np.uint8)
        live=LiveFoamRuntime()
        with patch('apps.vision.foam_live.FoamStreamInspector',return_value=detector), \
             patch.object(CameraAdapter,'acquire_frame',side_effect=capture), \
             patch.object(CameraAdapter,'decode_frame',side_effect=lambda frame:frame), \
             patch.object(CameraAdapter,'close_worker'):
            try:
                live.start()
                self.assertTrue(entered.wait(2))
                initial=live.status()['image']
                self.assertTrue(initial.startswith('data:image/jpeg'))
                deadline=time.monotonic()+2
                while live.status()['image']==initial and time.monotonic()<deadline:time.sleep(.02)
                self.assertNotEqual(live.status()['image'],initial)
                self.assertIsNone(live.status()['result'])
                with live.lock:live.error='connection lost'
                self.assertIsNone(live.status()['image'])
            finally:
                release.set()
                live.stop()

    def test_control_aliases_enter_and_resume_without_stopping_camera(self):
        with patch('apps.vision.foam_live.runtime') as live:
            live.status.return_value={}
            live.manual_status.return_value=False
            for action,enabled in [('start',True),('enter_manual',True),('stop',False),('resume_auto',False)]:
                response=self.client.post('/vision/api/foam/stream/live/control/',
                    data=json.dumps({'action':action}),content_type='application/json')
                self.assertEqual(response.status_code,200)
                live.set_manual.assert_called_with(enabled)
            live.stop.assert_not_called()

class FieldReadinessTests(SimpleTestCase):
    def test_decode_error_recovers_without_operator_restart(self):
        import time
        from .foam_live import LiveFoamRuntime
        from apps.devices.adapters.camera import CameraAdapter
        live=LiveFoamRuntime()
        detector=Mock()
        detector.process.side_effect=lambda frame,timestamp,frame_id:dict(state=NORMAL,sides={},timestamp=timestamp,frame_id=frame_id,elapsed_ms=1)
        calls=[0]
        def decode(raw):
            calls[0]+=1
            if calls[0]==1:raise ValueError('incomplete frame')
            return np.full((48,64),80,np.uint8)
        def capture(*args,**kwargs):time.sleep(.02);return {}
        with patch('apps.vision.foam_live.FoamStreamInspector',return_value=detector),patch.object(CameraAdapter,'acquire_frame',side_effect=capture),patch.object(CameraAdapter,'decode_frame',side_effect=decode),patch.object(CameraAdapter,'close_worker'):
            try:
                live.start();deadline=time.monotonic()+4
                while not live.status()['result'] and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(live.status()['running'])
                self.assertEqual(live.status()['result']['state'],NORMAL)
                self.assertEqual(live.status()['error'],'')
            finally:live.stop()

    def test_bundled_profile_fallback_respects_explicit_override(self):
        import os
        from .foam_video_sessions import profile_path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundled=root/'media/vision/foam_stream_templates/pic2/profile.json'
            bundled.parent.mkdir(parents=True);bundled.write_text('{}')
            missing=root/'external/profile.json'
            with override_settings(BASE_DIR=root,FOAM_STREAM_PROFILE=missing),patch.dict(os.environ,{},clear=True):
                self.assertEqual(profile_path(),bundled)
                with patch.dict(os.environ,{'FOAM_STREAM_PROFILE':str(missing)}):
                    self.assertEqual(profile_path(),missing)
