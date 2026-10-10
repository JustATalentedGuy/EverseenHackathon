"""Fast, network-free regression coverage for live dashboard contracts."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from prototype.live import summarize_window, select_live_model
from prototype.insights import sustained_pressure, make_recommendation
from prototype.sources import resolve_source
from prototype import server


class SourceTests(unittest.TestCase):
    def test_webcam_and_network_video(self):
        self.assertEqual(resolve_source('0', Path('.'))[0], 0)
        self.assertEqual(resolve_source('rtsp://localhost:8554/cam', Path('.'))[0],
                         'rtsp://localhost:8554/cam')
        self.assertEqual(resolve_source('https://example.org/clip.mp4', Path('.'))[1], True)

    def test_reject_unsafe_or_missing_sources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for src in ('', '../missing.mp4', 'file:///etc/passwd',
                        'ftp://example.org/a', '99', 'C:/Windows/win.ini'):
                with self.subTest(src=src), self.assertRaises(ValueError):
                    resolve_source(src, root)
            (root / 'demo.mp4').write_bytes(b'sample')
            self.assertEqual(resolve_source('demo.mp4', root)[1], False)


class StatsTests(unittest.TestCase):
    def test_recent_window_ignores_old_occupancy(self):
        rows = [{'time': 1, 'count': 100}, {'time': 400, 'count': 2},
                {'time': 420, 'count': 4}]
        self.assertEqual(summarize_window(rows, 420, 100)['mean'], 3)
        self.assertEqual(summarize_window(rows, 420, 100)['samples'], 2)

    def test_empty_window(self):
        self.assertEqual(summarize_window([{'time': 1, 'count': 9}], 400, 100)['p90'], 0)

    def test_live_export_is_optional_with_pytorch_fallback(self):
        with TemporaryDirectory() as tmp:
            chosen=select_live_model({'model':'models/yolo11n.pt','device':'cpu'},Path(tmp))
            self.assertEqual(chosen.name,'yolo11n.pt')

    def test_spikes_and_camera_gaps_do_not_trigger_recommendations(self):
        stable = [{'time': t, 'count': 4, 'slow_fraction': .8} for t in range(6)]
        self.assertIsNotNone(sustained_pressure(stable, threshold=4))
        self.assertIsNone(sustained_pressure(stable[:3], threshold=4))
        self.assertIsNone(sustained_pressure(stable+[{'time': 6, 'count': 0}], threshold=4))
        self.assertIsNone(sustained_pressure(stable[:3]+[
            {'time': t, 'count': 4, 'slow_fraction': .8} for t in range(30, 33)], threshold=4))

    def test_recommendation_is_role_specific_and_noncausal(self):
        evidence=sustained_pressure([{'time': t, 'count': 4} for t in range(8)], 4)
        cue=make_recommendation({'id':'checkout','label':'Front counter','role':'checkout'}, evidence)
        self.assertIn('staffing',cue['message'])
        self.assertIn('not proof',cue['note'].lower())
        self.assertEqual(cue['evidence']['support_samples'],8)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'prototype' / 'config_versions').mkdir(parents=True)
        (self.root / 'prototype' / 'dashboard.html').write_text('<title>Everseen dashboard</title>')
        (self.root / 'prototype' / 'index.html').write_text('<title>Everseen setup</title>')
        (self.root / 'demo.mp4').write_bytes(b'not decoded by API tests')
        self.config = {'schema_version': 1, 'cameras': [
            {'id': 'first', 'source': 'demo.mp4', 'zones': []}], 'zone_owners': {}}
        self.config_path = self.root / 'prototype' / 'site.json'
        self.config_path.write_text(json.dumps(self.config))
        self.patches = [patch.object(server, 'ROOT', self.root),
                        patch.object(server, 'CONFIG', self.config_path),
                        patch.object(server, 'DEMO_CATALOG', self.root / 'prototype' / 'demo_catalog.json'),
                        patch.object(server.live, 'stop_all')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(server.app)

    def test_page_and_status(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/setup').status_code, 200)
        self.assertEqual(self.client.get('/api/config').json(), self.config)

    def test_add_camera_and_reject_duplicate(self):
        added = self.client.post('/api/cameras', json={'name': 'Checkout', 'source': 'demo.mp4'})
        self.assertEqual(added.status_code, 200)
        another = self.client.post('/api/cameras', json={'name': 'Checkout', 'source': '0'})
        self.assertEqual(another.json()['id'], 'checkout_2')
        self.assertEqual(len(self.client.get('/api/config').json()['cameras']), 3)
        self.assertEqual(self.client.delete('/api/cameras/checkout').status_code, 200)

    def test_reject_invalid_source_without_config_mutation(self):
        r = self.client.post('/api/cameras', json={'name':'Outside','source':'../../Windows/win.ini'})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.client.get('/api/config').json(), self.config)

    def test_reject_invalid_inference_configuration(self):
        for key, value in [('sample_hz', 0), ('confidence', -1), ('cpu_threads', 0),
                           ('imgsz', 'invalid')]:
            with self.subTest(key=key):
                invalid = {**self.config, key: value}
                self.assertEqual(self.client.put('/api/config', json=invalid).status_code, 422)
        self.assertEqual(self.client.get('/api/config').json(), self.config)

    def test_reject_unapproved_business_zone_role(self):
        invalid=copy.deepcopy(self.config)
        invalid['cameras'][0]['zones']=[{'id':'z','polygon':[[.1,.1],[.9,.1],[.9,.9]],
                                         'role':'magic','crowd_threshold':4}]
        self.assertEqual(self.client.put('/api/config',json=invalid).status_code,422)

    def test_config_update_stops_live_before_reusing_zones(self):
        new = copy.deepcopy(self.config)
        new['cameras'][0]['zones'] = [{'id': 'checkout', 'polygon':
                                     [[.1,.1],[.9,.1],[.9,.9],[.1,.9]]}]
        r = self.client.put('/api/config', json=new)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(server.live.stop_all.call_count, 1)
        self.assertEqual(self.client.get('/api/config').json()['cameras'][0]['zones'][0]['id'], 'checkout')

    def test_prevent_cross_origin_config_changes(self):
        r = self.client.post('/api/cameras', json={'name':'Bad','source':'0'},
                             headers={'origin':'https://example.org'})
        self.assertEqual(r.status_code, 403)

    def test_demo_catalog_rejects_unvalidated_sources(self):
        catalog=[{'id':'sample','title':'Sample Video','source':'demo.mp4','validation_key':'sample',
                  'best_use':'testing','caveat':'fake','research_only':True,'role':'other'}]
        (self.root/'prototype'/'demo_catalog.json').write_text(json.dumps(catalog))
        data=self.client.get('/api/demo/catalog').json()['videos']
        self.assertEqual(data[0]['state'],'needs_validation')
        r=self.client.post('/api/demo/activate/sample')
        self.assertEqual(r.status_code,422)
        self.assertEqual(self.client.get('/api/config').json(),self.config)

    def test_demo_activation_is_idempotent_and_requires_validated_bytes(self):
        path=self.root/'demo.mp4'
        path.write_bytes(b'fake video bytes'*800)
        import hashlib
        catalog=[{'id':'sample','title':'Sample video','source':'demo.mp4','validation_key':'sample',
                  'best_use':'testing','caveat':'fake','research_only':True,'role':'other'}]
        (self.root/'prototype'/'demo_catalog.json').write_text(json.dumps(catalog))
        runs=self.root/'runs';runs.mkdir()
        (runs/'retail_demo_validation.json').write_text(json.dumps({'sample':{
          'path':'demo.mp4','status':'tested','samples_decoded':12,
          'nonempty_sample_fraction':1.,'file_bytes':path.stat().st_size,
          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}))
        class FakeCapture:
            def read(self):return True, object()
            def release(self):pass
        with patch.object(server.cv2,'VideoCapture',return_value=FakeCapture()):
            item=self.client.get('/api/demo/catalog').json()['videos'][0]
            self.assertTrue(item['available'])
            self.assertEqual(self.client.post('/api/demo/activate/sample').json()['id'],'demo_sample')
            self.assertEqual(self.client.post('/api/demo/activate/sample').json()['id'],'demo_sample')
        self.assertEqual(len(self.client.get('/api/config').json()['cameras']),2)
        path.write_bytes(b'replaced bad frames'*850)
        self.assertEqual(self.client.post('/api/demo/activate/sample').status_code,422)

    def test_growing_live_event_log_has_no_fixed_content_length(self):
        from types import SimpleNamespace
        path=self.root/'events.jsonl'
        path.write_bytes(b'{"camera":"first"}\n')
        with patch.object(server.live,'get',return_value=SimpleNamespace(events_path=path)):
            r=self.client.get('/api/live/events/first')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.text,'{"camera":"first"}\n')
        self.assertNotIn('content-length',r.headers)

    def test_heatmap_api_rejects_unsupported_time_ranges(self):
        with patch.object(server.live,'get',return_value=object()):
            self.assertEqual(self.client.get('/api/live/heat/first.jpg?window_s=45').status_code,422)
            self.assertEqual(self.client.get('/api/live/heat/first/summary?window_s=999').status_code,422)


if __name__ == '__main__':
    unittest.main()
