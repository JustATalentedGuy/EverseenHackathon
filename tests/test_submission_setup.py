"""Final release contracts: compatible demo seeds and modular browser assets."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from prototype import server
from prototype.topology import validate_layout


def camera(camera_id, source):
    return {'schema_version':1,'cameras':[{
        'id':camera_id,'source':source,'zones':[
            {'id':'floor_zone','label':'Floor','polygon':[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]}
        ]}]}


def floor(camera_id):
    return {'version':1,'sections':[{'id':'main_floor','name':'Floor area',
        'x':2,'y':4,'w':4,'h':4,'role':'entrance',
        'links':[{'camera_id':camera_id,'zone_id':'floor_zone'}]}]}


def test_first_run_falls_back_to_attributed_research_demo_without_cctv():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);proto=root/'prototype';proto.mkdir()
        (proto/'site_caviar.json').write_text(json.dumps(camera('research','datasets/research.mpg')))
        (proto/'site_cctv.json').write_text(json.dumps(camera('private','data/cctv/private.mp4')))
        (proto/'floor_layout_caviar.json').write_text(json.dumps(floor('research')))
        (proto/'floor_layout.json').write_text(json.dumps(floor('private')))
        with patch.object(server,'ROOT',root),patch.object(server,'CONFIG',proto/'site_runtime.json'),\
             patch.object(server,'LAYOUT',proto/'floor_layout_runtime.json'):
            actual=server.load()
            assert actual['cameras'][0]['id']=='research'
            layout=server.load_layout()
            validate_layout(layout,actual)
            assert layout['sections'][0]['links'][0]['camera_id']=='research'
            assert (proto/'site_runtime.json').is_file()


def test_preexisting_local_store_clips_select_corresponding_layout():
    with TemporaryDirectory() as tmp:
        root=Path(tmp);proto=root/'prototype';proto.mkdir()
        (proto/'site_caviar.json').write_text(json.dumps(camera('research','datasets/research.mpg')))
        (proto/'site_cctv.json').write_text(json.dumps(camera('private','data/cctv/private.mp4')))
        (proto/'floor_layout_caviar.json').write_text(json.dumps(floor('research')))
        (proto/'floor_layout.json').write_text(json.dumps(floor('private')))
        path=root/'data'/'cctv'/'private.mp4';path.parent.mkdir(parents=True);path.write_bytes(b'local')
        with patch.object(server,'ROOT',root),patch.object(server,'CONFIG',proto/'site_runtime.json'),\
             patch.object(server,'LAYOUT',proto/'floor_layout_runtime.json'):
            actual=server.load()
            assert actual['cameras'][0]['id']=='private'
            validate_layout(server.load_layout(),actual)
            assert server.load_layout()['sections'][0]['links'][0]['camera_id']=='private'


def test_static_browser_assets_and_assistant_are_available():
    with TestClient(server.app) as client:
        for url in ['/assets/dashboard.css','/assets/dashboard.js','/assets/layout.css',
                    '/','/layout','/api/assistant/capabilities','/api/briefing/config']:
            r=client.get(url)
            assert r.status_code==200,(url,r.status_code,r.text[:150])
