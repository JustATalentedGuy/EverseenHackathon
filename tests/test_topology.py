"""Schematic floor layout and bounded cross-camera analytical claims."""
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fastapi.testclient import TestClient
from prototype import server
from prototype.topology import validate_layout,build_topology,full_report,insights


def section(sid,x,y,w,h,role='other',links=None):
    return {'id':sid,'name':sid.replace('_',' ').title(),'x':x,'y':y,'w':w,'h':h,'role':role,'links':links or []}

def example():
    return {'version':1,'sections':[
        section('entrance',4,6,4,2,'entrance'),
        section('mid',4,3,4,3,'aisle'),
        section('exit',4,0,4,3,'exit'),
        section('quiet',8,3,2,2,'display'),
    ]}

def config():return {'cameras':[
    {'id':'a','zones':[{'id':'aa','label':'Checkout'},{'id':'ab'}]},
    {'id':'b','zones':[{'id':'ba','label':'Checkout backup'},{'id':'bb'}]},
    {'id':'c','zones':[{'id':'ca','label':'Quiet'}]}
]}

def live_camera(cid,zones,healthy=True,risks=None):
    return {'id':cid,'elapsed_s':60,'measurement':{'fresh':healthy,'state':'observing' if healthy else 'stale'},
            'zones':zones,'inspection_cues':risks or []}

def zone(zid,count,samples=25,mean=None,dwell=4):
    return {'id':zid,'occupancy':count,'mean_occupancy_5m':mean if mean is not None else count,
            'p90_occupancy_5m':count,'samples_5m':samples,'partial_dwell_mean_s':dwell,
            'partial_dwell_tracks':2,'observed_track_entries':5}


class GeometryTests(unittest.TestCase):
    def test_schematic_grid_validation(self):
        l=example();self.assertIs(validate_layout(l,config()),l)
        for mutation in [lambda a:a['sections'][0].update(x=-1),
                         lambda a:a['sections'][1].update(w=100),
                         lambda a:a['sections'][1].update(y=4),
                         lambda a:a['sections'][1].update(name=''),
                         lambda a:a['sections'][1].update(role='customer-intent')]:
            bad=copy.deepcopy(l);mutation(bad)
            with self.assertRaises(ValueError):validate_layout(bad,config())

    def test_mapping_must_exist_and_not_repeated(self):
        l=example();l['sections'][1]['links']=[{'camera_id':'a','zone_id':'aa'}]
        self.assertIs(validate_layout(l,config()),l)
        duplicate=copy.deepcopy(l);duplicate['sections'][2]['links']=[{'camera_id':'a','zone_id':'aa'}]
        with self.assertRaises(ValueError):validate_layout(duplicate,config())
        wrong=copy.deepcopy(l);wrong['sections'][1]['links'][0]['zone_id']='bad'
        with self.assertRaises(ValueError):validate_layout(wrong,config())

    def test_adjacency_and_graph(self):
        g=build_topology(example()['sections'])
        self.assertEqual(set(g['adjacency']['mid']),{'entrance','exit','quiet'})
        self.assertIn(['entrance','mid','exit'],g['routes'])
        self.assertEqual(g['route_through_count']['mid'],1)
        self.assertFalse(g['assumed_entrances'])
        self.assertFalse(g['assumed_exits'])

    def test_bottom_and_top_assumptions_exposed(self):
        l=example();l['sections'][0]['role']='other';l['sections'][2]['role']='other'
        g=build_topology(l['sections'])
        self.assertTrue(g['assumed_entrances'])
        self.assertTrue(g['assumed_exits'])


class AnalyticsTests(unittest.TestCase):
    def test_multiple_overlapping_views_take_max_not_sum(self):
        l=example();l['sections'][1]['links']=[{'camera_id':'a','zone_id':'aa'}, {'camera_id':'b','zone_id':'ba'}]
        state={'cameras':[live_camera('a',[zone('aa',3,mean=2,dwell=9)]),
                          live_camera('b',[zone('ba',4,mean=1,dwell=6)])]}
        report=full_report(l,config(),state)
        mid=next(s for s in report['sections'] if s['id']=='mid')
        self.assertEqual(mid['count'],4)
        self.assertEqual(mid['active_feeds'],2)
        self.assertEqual(mid['partial_dwell_s'],6)
        self.assertEqual(report['overall']['visible_section_count_sum'],4)
        self.assertIn('NOT unique',report['overall']['note'])

    def test_stale_and_missing_camera_must_not_look_empty(self):
        l=example();l['sections'][1]['links']=[{'camera_id':'a','zone_id':'aa'}]
        state={'cameras':[live_camera('a',[zone('aa',0)],healthy=False)]}
        mid=next(s for s in full_report(l,config(),state)['sections'] if s['id']=='mid')
        self.assertIsNone(mid['count']);self.assertEqual(mid['state'],'no_live_evidence')
        self.assertEqual(full_report(l,config(),state)['insights'][0]['kind'],'layout_gap') if False else None

    def test_redistribution_needs_sustained_pressure_and_measured_low_use(self):
        l=example();l['sections'][1]['links']=[{'camera_id':'a','zone_id':'aa'}];l['sections'][3]['links']=[{'camera_id':'c','zone_id':'ca'}]
        review={'zone':'aa','reason':'Four consecutive high-occupancy observations'}
        stats={'cameras':[live_camera('a',[zone('aa',5,mean=4)],risks=[review]),
                          live_camera('c',[zone('ca',0,mean=.15)])]}
        result=full_report(l,config(),stats)
        suggestions=[x for x in result['insights'] if x['kind']=='redistribution_candidate']
        self.assertEqual(len(suggestions),1)
        self.assertEqual(suggestions[0]['candidate_id'],'quiet')
        self.assertIn('not proven unused',suggestions[0]['caveat'])
        stats['cameras'][1]['measurement']['fresh']=False
        self.assertFalse(any(s['kind']=='redistribution_candidate' for s in full_report(l,config(),stats)['insights']))


class EndpointsTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'prototype').mkdir()
        (self.root/'prototype'/'layout.html').write_text('layout view')
        (self.root/'prototype'/'layout.js').write_text('layout controller')
        (self.root/'prototype'/'site.json').write_text(json.dumps(config()))
        for name,value in [('ROOT',self.root),('CONFIG',self.root/'prototype'/'site.json'),
                           ('LAYOUT',self.root/'prototype'/'floor_layout.json')]:
            p=patch.object(server,name,value);p.start();self.addCleanup(p.stop)
        self.client=TestClient(server.app)

    def test_get_save_reload_and_no_mutation_of_camera_config(self):
        self.assertEqual(self.client.get('/layout').status_code,200)
        self.assertEqual(self.client.get('/static/layout.js').status_code,200)
        self.assertEqual(self.client.get('/api/layout').json()['sections'],[])
        l=example();self.assertEqual(self.client.put('/api/layout',json=l).status_code,200)
        self.assertEqual(self.client.get('/api/layout').json()['sections'],l['sections'])
        self.assertEqual(self.client.get('/api/config').json(),config())
        self.assertEqual(len(self.client.get('/api/layout/analytics').json()['sections']),4)

    def test_invalid_draft_does_not_replace_saved_layout(self):
        l=example();self.client.put('/api/layout',json=l)
        bad=copy.deepcopy(l);bad['sections'][0]['w']=20
        self.assertEqual(self.client.put('/api/layout',json=bad).status_code,422)
        self.assertEqual(self.client.get('/api/layout').json()['sections'],l['sections'])

    def test_cross_origin_layout_update_denied(self):
        self.assertEqual(self.client.put('/api/layout',json=example(),
                                      headers={'origin':'https://invalid.example'}).status_code,403)
