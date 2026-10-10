"""Assistant, retrieval and briefing tests. Run: python -m pytest tests -q  (or python tests/test_assistant.py)"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prototype import assistant as A, assistant_docs as D, briefing as B

STATS = {
    'id': 'cam1', 'name': 'Corridor', 'status': 'live', 'frames': 240,
    'zones': [
        {'id': 'corridor_middle', 'label': 'Corridor observation region', 'role': 'aisle',
         'crowd_threshold': 4, 'occupancy': 7, 'peak': 7, 'observed_track_entries': 41,
         'partial_dwell_mean_s': 8.3, 'partial_dwell_tracks': 9, 'p90_occupancy_5m': 5,
         'mean_occupancy_5m': 3.2, 'samples_5m': 120},
        {'id': 'store_front', 'label': 'Store front', 'role': 'entrance', 'crowd_threshold': 4,
         'occupancy': 0, 'peak': 2, 'observed_track_entries': 6, 'partial_dwell_mean_s': 0.0,
         'partial_dwell_tracks': 0, 'p90_occupancy_5m': 1, 'mean_occupancy_5m': 0.4, 'samples_5m': 120},
    ],
    'inspection_cues': [{'zone': 'corridor_middle', 'zone_label': 'Corridor observation region',
                         'zone_role': 'aisle', 'message': 'Check aisle clearance.',
                         'evidence': {'duration_s': 6.0, 'support_samples': 12, 'minimum_observed': 7}}],
    'measurement': {'state': 'observing', 'fresh': True, 'age_s': 0.4, 'observed_fps_30s': 4.9,
                    'target_hz': 5.0, 'backend': 'pt'},
    'scope': 'Observed camera-local tracks and partial visible dwell only',
}


def make_assistant(tmpdir, stats=None):
    log = Path(tmpdir) / 'observations.jsonl'
    with log.open('w') as handle:
        for i in range(120):
            handle.write(json.dumps({
                'camera': 'cam1', 'time_s': i * 0.5,
                'counts': {'corridor_middle': 7 if i >= 90 else 2, 'store_front': 1},
                'observations': [], 'inspection_cues': []}) + '\n')

    payload = stats or STATS

    class Cam:
        events_path = log
        def stats(self): return payload

    class Live:
        sessions = {'cam1': None}
        def get(self, camera_id): return Cam() if camera_id == 'cam1' else None

    return A.Assistant(Live(), D.build_index(ROOT))


def test_refuses_unsupported_claims():
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        for question in ['how many unique shoppers came today', 'what was the average checkout wait time',
                         'how long do people wait in the queue', 'what is our revenue',
                         'who is that person in the video']:
            result = a.answer(question)
            assert result['route'] == 'refusal', question
            assert 'cannot report' in result['answer'].lower()


def test_metric_answers_use_measured_values():
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        result = a.answer('how many people are in the corridor observation region right now')
        assert result['route'] == 'metric'
        assert '7' in result['answer']            # value taken from STATS, not invented
        assert 'observations.jsonl' in result['sources'] or 'live.stats()' in result['sources']

        dwell = a.answer('what is the average dwell time')
        assert '8.3' in dwell['answer']
        assert 'partial' in dwell['answer'].lower()


def test_definition_answers_without_a_camera():
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        result = a.answer('what does partial visible dwell mean')
        assert result['route'] == 'document'
        assert result['sources']


def test_stale_data_leads_with_the_caveat():
    stale = json.loads(json.dumps(STATS))
    stale['measurement']['state'] = 'stale'
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp, stats=stale)
        result = a.answer('how many people are in the corridor observation region')
        assert 'last frame' in result['answer'].lower()
        assert result['answer'].lower().startswith(('no recent frame', 'the model', 'processing'))


def test_briefing_link_is_free_and_encoded():
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        summary = B.build_summary(a)
        assert len(summary['text']) <= 1000
        link = B.wa_link('+919000000000', summary['text'])
        assert link.startswith('https://wa.me/919000000000?text=')
        from urllib.parse import parse_qs, urlparse
        assert parse_qs(urlparse(link).query)['text'][0].startswith('Store briefing')


def test_recipient_validation():
    assert B.validate_recipient({'name': 'A', 'number': '910000000000'})['number'] == '+910000000000'
    for bad in [{'name': 'A', 'number': '123'}, {'name': '', 'number': '+919000000000'}]:
        try:
            B.validate_recipient(bad)
            raise AssertionError('should have been rejected: %s' % bad)
        except ValueError:
            pass


def test_schedule_loop_never_hangs():
    with tempfile.TemporaryDirectory() as tmp:
        # Point the briefing at a scratch directory: tests must never rewrite the
        # real recipient list in prototype/assistant_config.json.
        scratch = Path(tmp) / 'state'
        original_config, original_log = B.CONFIG, B.LOG
        B.CONFIG, B.LOG = scratch / 'assistant_config.json', scratch / 'deliveries.jsonl'
        try:
            a = make_assistant(tmp)
            service = B.BriefingService(a)
            service.update({'recipients': [{'name': 'A', 'number': '+919000000000'}],
                            'frequency_minutes': 60})
            snapshot = service.snapshot()      # update() calls snapshot(): must not deadlock
            assert snapshot['recipients'][0]['number'] == '+919000000000'
            assert B.CONFIG.exists() and str(B.CONFIG).startswith(str(scratch))
        finally:
            B.CONFIG, B.LOG = original_config, original_log


def test_auto_backend_routes_to_llamacpp():
    """ASSISTANT_BACKEND=auto must detect llama.cpp and then talk to it, not to Ollama."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from prototype import assistant_llm

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, code=200):
            raw = _json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self._send({'status': 'ok'}) if self.path == '/health' else self._send({'models': []}, 404)

        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            body = _json.loads(self.rfile.read(length) or b'{}')
            seen.append(self.path)
            self._send({'choices': [{'message': {'content': 'The corridor has 7 people right now.'}}]})

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = assistant_llm.LLAMACPP_URL
    try:
        assistant_llm.LLAMACPP_URL = 'http://127.0.0.1:%d' % server.server_port
        phraser = assistant_llm.Phraser(backend='auto', gguf=__file__)   # a real file stands in for the GGUF
        assert phraser.ready(), 'llama.cpp should have been detected'
        assert phraser._ready == 'llamacpp'
        text = phraser.phrase('how many people', 'Corridor currently shows 7 observed people.',
                              {'measurement': {'state': 'observing'}, 'zones': [], 'cues': []})
        assert text == 'The corridor has 7 people right now.'
        assert seen == ['/v1/chat/completions']
    finally:
        assistant_llm.LLAMACPP_URL = original
        server.shutdown()
        server.server_close()


def test_bottleneck_questions_answer_from_observations():
    """Bottleneck/dead-zone questions must be measured, never a documentation quote."""
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        for question in ['what are the bottlenecks', 'where are the dead zones',
                         'which zone is congested', 'any dead zones', 'is anything blocked']:
            result = a.answer(question)
            assert result['route'] == 'metric', f'{question} -> {result["route"]}'
            text = result['answer']
            # A retrieval quote would bring bibliography or notation with it.
            for leak in ('DOI:', 'http', '**', 'Normalized', 'severity_area', 'et al'):
                assert leak not in text, f'{question} leaked {leak!r}: {text[:120]}'
            assert len(text) < 700, text


def test_bottleneck_ranking_reflects_duration_not_peak():
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        long_ev = {'duration_s': 22.0, 'support_samples': 40, 'minimum_observed': 4, 'peak_observed': 5}
        spike_ev = {'duration_s': 6.0, 'support_samples': 12, 'minimum_observed': 3, 'peak_observed': 11}
        a.answer('what are the bottlenecks')                 # warm the payload
        result = a.answer('what are the bottlenecks')
        assert result['route'] == 'metric'
        text = a.compose_metric('what are the bottlenecks', {
            'measurement': {'state': 'observing', 'reliable': True, 'text': 'ok'},
            'zones': [], 'cues': [
                {'zone': 'a', 'zone_label': 'Spike zone', 'evidence': spike_ev},
                {'zone': 'b', 'zone_label': 'Sustained zone', 'evidence': long_ev}],
            'intent': 'bottleneck'})
        assert text.index('Sustained zone') < text.index('Spike zone')
        assert 'brief spike' in text and 'sustained blockage' in text


def test_stale_camera_never_prints_a_none_count():
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        text = a.compose_metric('what are the bottlenecks', {
            'measurement': {'state': 'stale', 'reliable': False, 'text': 'No recent frame'},
            'zones': [{'label': 'Atrium floor', 'occupancy': None, 'peak': 9, 'entries': 4}],
            'cues': [], 'intent': 'bottleneck'})
        assert 'None' not in text, text


def test_dead_zone_answer_is_caveated():
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        text = a.compose_metric('where are the dead zones', {
            'measurement': {'state': 'observing', 'reliable': True, 'text': 'ok'},
            'zones': [{'label': 'Quiet corner', 'entries': 0, 'peak': 0, 'mean_5m': 0.0}],
            'cues': [], 'intent': 'dead'})
        assert 'Quiet corner' in text
        assert 'not proof' in text.lower() or 'cannot see' in text.lower()


def test_spoken_answers_are_short_answer_first_and_hook():
    """Voice output must read like a person, not a metrics dump."""
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        for q in ['how many people are here', 'what are the bottlenecks', 'where are the dead zones',
                  'what is the average dwell time', 'what alerts are active', 'give me a summary']:
            r = a.answer(q)
            assert r.get('spoken'), f'no spoken variant for {q!r}'
            text = r['spoken']
            assert len(text) < 260, f'{q}: too long for speech -> {text}'
            sentences = [x for x in text.replace('!', '.').split('.') if x.strip()]
            assert len(sentences) <= 4, f'{q}: {len(sentences)} sentences -> {text}'
            # a spoken answer must invite a follow-up rather than dump and stop
            assert text.rstrip().endswith('?'), f'{q}: no conversational hook -> {text}'
            # screen-only jargon must never be spoken
            for jargon in ('observed', 'camera-local', 'partial visible dwell', 'p90', 'p90th',
                           'percentile', 'observed_track'):
                assert jargon not in text.lower(), f'{q}: spoke {jargon!r} -> {text}'


def test_spoken_answers_never_speak_bare_digits_lists():
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp)
        text = a.answer('how many people are here')['spoken']
        # a spoken answer must not dump a per-zone list
        assert ';' not in text, f'zone list spoken -> {text}'
        assert text.count(',') <= 4, f'too many clauses, sounds like a list -> {text}'


def test_stale_data_leads_the_spoken_answer():
    stale = json.loads(json.dumps(STATS)); stale['measurement']['state'] = 'stale'
    with tempfile.TemporaryDirectory() as tmp:
        a = make_assistant(tmp, stats=stale)
        text = a.answer('how many people are here')['spoken']
        assert text.lower().startswith('heads up'), text


def test_cloud_backend_is_used_when_a_key_is_present():
    """Cloud is the auto-detected last resort, and it never invents numbers."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from prototype import assistant_llm

    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            seen['auth'] = self.headers.get('Authorization')
            seen['body'] = _json.loads(self.rfile.read(length) or b'{}')
            raw = _json.dumps({'choices': [{'message': {
                'content': 'The main aisle has five people in it, so you can leave it be.'}}]}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

        def log_message(self, *a):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    original = {k: getattr(assistant_llm, k) for k in ('CLOUD_URL', 'CLOUD_KEY', 'CLOUD_MODEL', 'LLAMACPP_URL')}
    try:
        assistant_llm.CLOUD_URL = 'http://127.0.0.1:%d/v1' % server.server_port
        assistant_llm.CLOUD_KEY = 'test-key-not-real'
        assistant_llm.CLOUD_MODEL = 'test-model'
        phraser = assistant_llm.Phraser(backend='cloud')
        assert phraser.ready(), 'cloud should be detected when a key is set'
        assert phraser._ready == 'cloud'
        text = phraser.phrase('how many people', 'Main aisle currently shows 5 observed people.',
                              {'measurement': {'state': 'observing'}, 'zones': [], 'cues': []})
        assert text.startswith('The main aisle')
        assert seen['auth'] == 'Bearer test-key-not-real'
        # the contract must reach the model, and no key may appear in the prompt
        assert 'ANSWER FIRST' in seen['body']['messages'][0]['content']
        assert 'test-key-not-real' not in _json.dumps(seen['body']['messages'])
    finally:
        for k, v in original.items():
            setattr(assistant_llm, k, v)
        server.shutdown(); server.server_close()


def test_no_key_means_no_cloud():
    from prototype import assistant_llm
    original = (assistant_llm.CLOUD_KEY, assistant_llm.GGUF)
    try:
        assistant_llm.CLOUD_KEY = ''
        assistant_llm.GGUF = ''
        assert assistant_llm.Phraser(backend='cloud').ready() is False
        assert assistant_llm.Phraser(backend='auto').ready() is False
    finally:
        assistant_llm.CLOUD_KEY, assistant_llm.GGUF = original


if __name__ == '__main__':
    for name, test in sorted(globals().items()):
        if name.startswith('test_'):
            test()
            print('pass', name)
    print('all assistant tests passed')