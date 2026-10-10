"""Evidence-gated store assistant: deterministic tools + document retrieval + refusal rules.

Numbers never come from the model. Metric answers are read from the same
`live.stats()` / observation log the dashboard renders; explanatory answers are
retrieved from the project documents. The optional LLM only routes intent and
phrases a sentence around values that were already computed here.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from . import assistant_docs

ROOT = Path(__file__).resolve().parents[1]

# Claims the system deliberately cannot support (see prototype/INTEGRATION.md).
UNSUPPORTED = [
    (r'\b(unique|distinct|total)\s+(shoppers?|visitors?|people|customers?)\b',
     'store-wide unique visitor counts'),
    (r'\b(total|overall|store[- ]?wide)\s+(footfall|traffic|visitors?|people)\b',
     'cross-camera deduplicated totals'),
    (r'\b(queue|queuing)\b|\b(checkout|cashier|till)\s+wait\b|\bwait(ing)?\s+(time|times)\b',
     'completed checkout waits'),
    (r'\b(bottleneck|blocked|congestion)\s+(caused|because|due to)\b', 'causal bottleneck claims'),
    (r'\b(revenue|sales|lost sales|conversion|basket|profit|margin|shrink)\b', 'revenue or conversion'),
    (r'\b(staff|employee|shopper)\s+(vs|versus|or)\b', 'staff versus shopper classification'),
    # The prototype sees people, never roles or rosters, so any staff question is unanswerable.
    (r'\b(staff|employees?|workers?|clerks?|roster|shift)\b', 'staff identity or headcount'),
    (r'\b(who|whose|identity|face|recognis|recogniz)\b', 'identifying anyone on camera'),
    (r'\b(which|what|whose)\s+(customer|shopper|person|people|individual)\b', 'identifying anyone on camera'),
    (r'\b(best|worst)\s+employee|\bperformance\s+of\b', 'staff performance'),
]

NUM_WORDS = r'(?:how many|persons?|people|count|occupancy|occupied|busy|crowded|empty)'
# A definition question asks what something *is*, not what it currently measures.
# It must win over a metric keyword like "dwell" that happens to appear in it.
DEFINITION_MARKERS = r'\b(meaning|mean|means|define|definition|explain|stands for)\b'
# "how do I know if X" asks for the rule behind the metric, so the documents answer it,
# even though it names a metric the live path would otherwise claim.
OPERATIONAL_DOCS = ('prototype/INTEGRATION.md', 'prototype/README.md', 'README.md')
RULE_MARKERS = (r'\bhow do i know\b|\bhow would you know\b|\bhow do you (?:decide|know|judge)\b'
                r'|\bwhat counts\b|\bwhat makes\b|\bwhen is .*flagged\b'
                r'|\bhow is .*(?:defined|calculated|measured|decided)\b')

# intent -> (regex, handler key)
METRIC_INTENTS = [
    ('health',    r'(measurement|fps|frame rate|stale|throughput|health|fresh|warm)'),
    ('cues',      r'(alert|cue|warning|flag|review|recommend|suggestion|problem|worried|worry|concern|trouble|troubling|attention)'),
    ('bottleneck', r'(bottleneck|blocked|blocking|congestion|congested|crowd(ed|ing)?|jam|gridlock|choke)'),
    ('dead',      r'(dead[ _-]?zone|dead ?spot|underused|under[ -]?used|unused|empty|deserted|idle|never used)'),
    ('trends',    r'(trend|over time|last \d+|peak(est)? time|when did|history|first \d+)'),
    ('summary',   r'(summar|overview|status|how is|how\'s|report|brief|everything)'),
    ('dwell',     r'(dwell|linger|lingering|how long|stay|staying|stayed)'),
    ('occupancy', rf'({NUM_WORDS}|occupancy)'),
    ('entries',   r'(track entries|entries|tracks|how many times|repeat)'),
]
DOC_INTENTS = [
    ('accuracy',  r'(accuracy|f1|mota|idf1|benchmark|test result|measured|false positive|miss)'),
    ('meaning',   r'(what (does|do|is|are)|meaning|define|definition|explain|means)'),
    ('limits',    r'(limitation|caveat|can\'t|cannot|not prove|trust|reliable|assumption)'),
    ('why',       r'(why|how does|how do|reason|cause)'),
]


def _matches(patterns, question):
    q = question.lower()
    return [name for name, pat in patterns if re.search(pat, q)]


def refusal(question):
    """Return the unsupported claim name, or None when the question is allowed."""
    q = question.lower()
    for pat, name in UNSUPPORTED:
        if re.search(pat, q):
            return name
    return None


def _fmt(value, digits=1):
    if value is None:
        return 'unavailable'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, float):
        return f"{value:.{digits}f}".rstrip('0').rstrip('.')
    return str(value)


def zone_lines(camera_id, stats):
    """One measured line per zone. All values come from live.stats()."""
    lines = []
    for z in stats.get('zones', []):
        label = z.get('label') or z['id']
        lines.append({
            'zone': z['id'], 'label': label, 'role': z.get('role', 'other'),
            'occupancy': z.get('occupancy'), 'peak': z.get('peak'),
            'p90': z.get('p90_occupancy_5m'), 'mean_5m': z.get('mean_occupancy_5m'),
            'entries': z.get('observed_track_entries'),
            'dwell_s': z.get('partial_dwell_mean_s'),
            'dwell_tracks': z.get('partial_dwell_tracks'),
            'threshold': z.get('crowd_threshold'),
        })
    return lines


def health_note(stats):
    m = stats.get('measurement', {})
    state = m.get('state', 'unknown')
    text = {
        'observing': 'Data is being observed normally',
        'warming': 'The model is still warming up, so early counts are unreliable',
        'limited': 'Processing is below half the target sample rate, so counts may miss activity',
        'stale': 'No recent frame has been processed, so the live figures are not current',
        'no_data': 'No frames have been processed yet',
    }.get(state, f"Measurement state is {state}")
    if m.get('age_s') is not None:
        text += f" (last frame {_fmt(m['age_s'])}s ago, {_fmt(m.get('observed_fps_30s'))} fps against a {_fmt(m.get('target_hz'))} Hz target)"
    return {'state': state, 'reliable': state == 'observing', 'text': text}


ONES = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
        'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen',
        'eighteen', 'nineteen', 'twenty']


def say_count(value):
    """Numbers are read aloud, not displayed: 3 -> 'three', 17 -> 'seventeen'."""
    if value is None:
        return 'no'
    value = int(value)
    if 0 <= value <= 20:
        return ONES[value]
    return str(value)


def say_people(count, plural=None):
    if count == 1:
        return 'one person'
    return '%s people' % say_count(count)


def say_seconds(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 'a few seconds'
    if value < 1:
        return 'under a second'
    if value < 90:
        return 'about %s seconds' % (ONES[int(round(value))] if round(value) <= 20 else int(round(value)))
    return 'about %d minutes' % round(value / 60)


def say_measurement(reliable):
    return 'Data looks healthy' if reliable else 'Quick warning before I answer'


def busiest(zones):
    live = [z for z in zones if z.get('occupancy')]
    pool = live or [z for z in zones if z.get('entries')]
    if not pool:
        return None
    key = 'occupancy' if live else 'entries'
    return max(pool, key=lambda z: (z.get(key) or 0, z.get('peak') or 0))


def trend_from_log(events, zone_id, window_s=300.0):
    """Peak and mean observed count for one zone over the observation log."""
    series = []
    for row in events:
        if zone_id and row.get('counts', {}).get(zone_id) is None:
            continue
        series.append(row)
    if not series:
        return None
    cutoff = series[-1].get('time_s', 0) - window_s
    series = [r for r in series if r.get('time_s', 0) >= cutoff] or series[-1:]
    for name in (zone_id,) if zone_id else sorted(series[-1].get('counts', {})):
        values = [r['counts'].get(name) for r in series if r.get('counts', {}).get(name) is not None]
        if values:
            return {'zone': name, 'samples': len(values), 'peak': max(values),
                    'mean': sum(values) / len(values),
                    'window_s': round(series[-1].get('time_s', 0) - series[0].get('time_s', 0), 1)}
    return None


def read_events(path, limit=4000):
    if not path or not Path(path).exists():
        return []
    rows = []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


_MARKDOWN_NOISE = re.compile(
    r'\[([^\]]+)\]\([^)]+\)'          # links -> text
    r'|\*\*|\*|`{1,3}'                 # emphasis and code ticks
    r'|\$[^$]*\$'                      # inline math
    r'|^\s*[|:#-]{2,}.*$'              # table rows and rules
    r'|^\s*[-*+]\s+',                  # bullet markers
    flags=re.M)


def _plain(text, query='', max_sentences=4, max_chars=520):
    """Turn a retrieved chunk into something a shopkeeper can actually read.

    The corpus is written for engineers: markdown tables, LaTeX and paper citations all
    reach this point, and reading them aloud is useless.
    """
    cleaned = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    cleaned = _MARKDOWN_NOISE.sub(' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if s.strip()]
    out = []
    for sentence in sentences:
        # skip bibliography entries, formula fragments and mid-clause remainders
        if re.search(r'doi:|arxiv|^\W*$', sentence, re.I):
            continue
        if re.search(r'[=∫Σ<>]|\bsum\b|\bintegral\b|\bnormalized congestion\b', sentence, re.I):
            continue
        if re.search(r'\b[A-Za-z]_\w+\s*\(|\(\s*t\s*\)|\bthreshold\b\s*$', sentence):
            continue
        if sentence.lstrip().startswith('...') or not sentence[:1].isupper():
            continue                      # a capitalised start means a real sentence
        if re.match(r'^(see|refer to|details in|for full|read )\b', sentence, re.I):
            continue                      # a cross-reference is not an explanation
        if len(sentence.split()) < 5:
            continue
        out.append((sentence, set(re.findall(r'[a-z]{4,}', (query or '').lower()))))
    if out:
        # keep the sentences that overlap the question most, but restore reading order
        def _score(item):
            words = set(re.findall(r'[a-z]{4,}', item[0].lower()))
            return len(item[1] & words) / (len(item[1]) or 1)
        best = sorted(out, key=_score, reverse=True)[:max_sentences]
        out = [sentence for sentence, _ in sorted(best, key=lambda x: out.index(x))]
    text_out = ' '.join(out)
    if not text_out:
        return ''
    if len(text_out) > max_chars:
        # drop the trailing partial sentence rather than cutting mid-clause
        kept = [x for x in out if len(' '.join(out[:out.index(x) + 1])) <= max_chars]
        text_out = ' '.join(kept) if kept else out[0][:max_chars].rsplit(' ', 1)[0]
    return text_out.rstrip(' ,;.') + '.'


def spoken_meaning(z):
    """_meaning() phrased for the ear."""
    occupancy, threshold = z.get('occupancy'), z.get('threshold')
    if occupancy is None:
        return 'though I have no current count'
    if threshold and occupancy >= threshold:
        return 'which is at or over your %s person limit' % _fmt(threshold)
    if threshold:
        return 'which is under your %s person limit' % _fmt(threshold)
    return 'and there is no review limit set for it'


def _meaning(z):
    """Plain-language reading of a zone against the operator's own review threshold."""
    occupancy = z.get('occupancy')
    threshold = z.get('threshold')
    if occupancy is None:
        return 'no current count'
    if threshold:
        if occupancy >= threshold:
            return 'at or over your %s-person review limit' % _fmt(threshold)
        if occupancy >= max(1, int(threshold * 0.7)):
            return 'approaching your %s-person review limit' % _fmt(threshold)
        return 'comfortably under your %s-person review limit' % _fmt(threshold)
    return '%s people right now' % _fmt(occupancy)


class Assistant:
    """Stateless facade used by the FastAPI layer. No model is required to answer."""

    def __init__(self, live_manager, docs=None, context=None):
        self.live = live_manager
        # context() -> {'config':…, 'status':…} lets the assistant use the operator's
        # drawn floor layout, which carries store-wide dwell and bottleneck analytics.
        self.context = context or (lambda: {})
        self.docs = docs if docs is not None else assistant_docs.build_index(ROOT)
        self.llm = None            # injected lazily; see assistant_llm
        self._lock = threading.RLock()

    # ---- store-wide analytics ---------------------------------------------
    def store(self):
        """Merge the drawn layout with live observations via the topology module.

        Returns {'has_layout', 'sections', 'cues'}. When no layout has been drawn the
        assistant falls back to per-camera zones, which cover less but never invent.
        """
        try:
            from . import topology
        except Exception:
            return {'has_layout': False, 'sections': [], 'cues': []}
        context = self.context() or {}
        config = context.get('config') or {}
        status = context.get('status') or {'cameras': []}
        try:
            import json as _json
            layout_path = Path(ROOT) / 'prototype' / 'floor_layout.json'
            layout = _json.loads(layout_path.read_text(encoding='utf-8')) if layout_path.exists() else {}
        except Exception:
            layout = {}
        sections = layout.get('sections') or []
        if not sections:
            return {'has_layout': False, 'sections': [], 'cues': []}
        try:
            topology.validate_layout(layout, config)
            data = topology.aggregate(layout, config, status)
            graph = topology.build_topology(sections)
            cues = topology.insights(data, graph)
        except Exception:
            return {'has_layout': True, 'sections': [], 'cues': []}
        return {'has_layout': True, 'sections': data, 'cues': cues}

    @staticmethod
    def _underused(sections):
        """The same rule topology.insights uses: measured, quiet, and not flagged.

        Deliberately stricter than "no track entries": an unmeasured area is not a dead
        zone, and the documentation says so.
        """
        verified = [s for s in sections if s.get('state') == 'observing'
                    and s.get('samples_5m', 0) >= 10]
        return [s for s in verified if not s.get('count') and s.get('mean_5m') is not None
                and s['mean_5m'] <= 0.5 and not s.get('review_evidence')]

    # ---- helpers -----------------------------------------------------------
    def _cameras(self):
        """Every camera the manager knows about.

        LiveManager exposes `cameras`; the test double exposes `sessions`. Reading the
        wrong one made every question that did not name a camera silently report no data.
        """
        for attribute in ('cameras', 'sessions'):
            registry = getattr(self.live, attribute, None)
            if isinstance(registry, dict):
                return list(registry)
        return []

    def _stats(self, camera_id=None):
        if camera_id:
            cam = self.live.get(camera_id)
            if cam is None:
                return None, None
            return cam.stats(), Path(cam.events_path)
        # default: the busiest live camera, else the first configured one
        best = None
        for cam_id in self._cameras():
            camera = self.live.get(cam_id)
            stats = camera.stats() if camera is not None else None
            if not stats or stats.get('status') != 'live':
                continue
            total = sum((z.get('occupancy') or 0) for z in stats.get('zones', []))
            if best is None or total > best[0]:
                best = (total, cam_id, stats)
        if best:
            cam = self.live.get(best[1])
            return best[2], Path(cam.events_path)
        cams = self._cameras()
        if not cams:
            return None, None
        cam = self.live.get(cams[0])
        return (cam.stats() if cam else None), (Path(cam.events_path) if cam else None)

    # ---- answer ------------------------------------------------------------
    def answer(self, question, camera_id=None, use_llm=True):
        question = (question or '').strip()
        if not question:
            return {'ok': False, 'answer': 'Ask a question about the current zone status.', 'route': 'empty'}

        blocked = refusal(question)
        if blocked:
            return {
                'ok': False, 'route': 'refusal', 'claim': blocked,
                'answer': ('I cannot report %s. This prototype observes camera-local tracks only and the '
                           'cameras are not verified as synchronized, so that number is not derivable. '
                           'I can report per-zone observed occupancy, partial visible dwell, observed track '
                           'entries and the review cues.' % blocked),
                'sources': ['prototype/INTEGRATION.md'],
            }

        wants_definition = re.search(DEFINITION_MARKERS, question.lower()) is not None
        asks_for_rule = re.search(RULE_MARKERS, question.lower()) is not None
        stats, events_path = self._stats(camera_id)
        if stats is None:
            # A documentation question does not need a live camera to be answerable.
            if wants_definition:
                payload = {'camera': None, 'measurement': {'state': 'no_data', 'reliable': False,
                                                           'text': 'No camera is monitoring'},
                           'zones': [], 'cues': [], 'definitions': self.docs.search(question, top=3),
                           'intent': 'meaning', 'trend': None}
                return {'ok': True, 'route': 'document', 'answer': self.compose_doc(question, payload),
                        'sources': [d['source'] for d in payload['definitions']],
                        'measurement': payload['measurement'], 'zones': [], 'cues': []}
            return {'ok': False, 'route': 'no_data',
                    'answer': 'No camera is monitoring right now, so there is nothing to report. '
                              'Start a camera on the dashboard and ask again.'}

        health = health_note(stats)
        zones = zone_lines(camera_id or stats.get('id'), stats)
        metric_hits = _matches(METRIC_INTENTS, question)
        doc_hits = _matches(DOC_INTENTS, question)
        if wants_definition or asks_for_rule:
            metric_hits = []          # a question about the rule belongs to the documents
        # "what is the measurement limitation" mentions "measurement", which the health intent
        # would otherwise claim; a limits question is a documentation question.
        if 'limits' in doc_hits and 'health' in metric_hits:
            metric_hits = [m for m in metric_hits if m != 'health']
        if not metric_hits:
            doc_hits = doc_hits or ['meaning']

        payload = {
            'camera': stats.get('name') or stats.get('id'),
            'measurement': health,
            'zones': zones,
            'cues': stats.get('inspection_cues', []),
            # Rule-seeking questions ask what this system does, so search the operational
            # docs; theory questions fall back to the whole corpus.
            # Hybrid retrieval: the static corpus explains, the live chunks report.
            'definitions': self._search(question, prefer=OPERATIONAL_DOCS if asks_for_rule else None,
                                        definitions=wants_definition) if doc_hits else [],
        }
        if doc_hits and not metric_hits:
            payload['trend'] = None

        # metric path: values are already in the payload, the model never computes them
        if metric_hits:
            events = read_events(events_path)
            zone_guess = self._zone_in_question(question, zones)
            payload['trend'] = trend_from_log(events, zone_guess)
            payload['intent'] = metric_hits[0]
            answer = self.compose_metric(question, payload)
            route = 'metric'
        else:
            payload['intent'] = (doc_hits or ['meaning'])[0]
            answer = self.compose_doc(question, payload)
            route = 'document'

        spoken = self.compose_spoken(question, payload) if route == 'metric' else None
        if use_llm and self.llm is not None:
            polished = self.llm.phrase(question, answer, payload)
            if polished:
                answer = polished
            # the voice line is what a shopkeeper actually hears, so it gets the same pass
            if spoken:
                spoken_polished = self.llm.phrase(question, spoken, payload)
                if spoken_polished:
                    spoken = spoken_polished
        return {'ok': True, 'route': route, 'answer': answer, 'spoken': spoken,
                'sources': self._sources(payload, route),
                'measurement': health, 'zones': zones, 'cues': payload['cues']}

    def _search(self, question, top=3, prefer=None, definitions=False):
        """Search the project documents and the ingested analytics corpus.

        No video is read here: assistant_ingest has already turned detector output into
        documents, and this is a plain retrieval over those.
        """
        # A definition lives in the documentation. The ingested analytics repeat the same
        # words with high frequency, so they would otherwise bury the explanation.
        exclude = ('runs/assistant/knowledge',) if definitions else None
        return self.docs.search(question, top=top, only=prefer, exclude=exclude)

    def _zone_in_question(self, question, zones):
        q = question.lower()
        for z in zones:
            for token in {z['label'].lower(), z['zone'].lower(), z['zone'].lower().replace('_', ' ')}:
                if token and token in q:
                    return z['zone']
        return None

    def _sources(self, payload, route):
        out = ['live.stats()']
        if route == 'metric' and payload.get('trend'):
            out.append('observations.jsonl')
        for d in payload.get('definitions', []):
            out.append(d['source'])
        return sorted(set(out))

    # ---- deterministic composition ----------------------------------------
    @staticmethod
    def _compose_story(zones, cues, trend=None):
        """The shift briefing: what is happening, why it matters, what to do next.

        Written as a supervisor would say it, not as a table of metrics. Every number
        still comes from measured values; the interpretation is only ever a comparison
        against the review threshold the operator set for that zone.
        """
        if not zones:
            return 'There are no floor zones set up yet, so there is nothing to report. ' \
                   'Draw a zone on the video and I will start watching it.'
        live = [z for z in zones if z.get('occupancy') is not None]
        sentences = []
        busiest_zone = max(live, key=lambda z: (z.get('occupancy') or 0, z.get('peak') or 0)) if live else None

        if not live:
            sentences.append('No zone has a current count right now, so I cannot tell you what is happening')
        else:
            count = busiest_zone.get('occupancy') or 0
            head = ('The busiest spot right now is %s, with %s people, %s'
                    % (busiest_zone['label'], _fmt(count), _meaning(busiest_zone)))
            if cues:
                head += ', and there %s' % ('is something worth checking' if len(cues) == 1
                                             else 'are %d things worth checking' % len(cues))
            elif count == 0:
                head += ', so the visible floor is empty'
            else:
                head += ', and nothing has crossed a review limit'
            sentences.append(head)

        quiet = [z for z in live if not z.get('entries') and not z.get('peak')]
        if quiet:
            sentences.append('%s has not seen anyone come through yet in this session'
                             % quiet[0]['label'])

        if trend and trend.get('zone') != (busiest_zone or {}).get('zone'):
            label = next((z['label'] for z in zones if z.get('zone') == trend.get('zone')), None)
            if label:
                sentences.append('over the last %ss, %s peaked at %s'
                                 % (_fmt(trend['window_s']), label, _fmt(trend['peak'])))

        lingered = [z for z in zones if z.get('dwell_tracks')]
        if lingered:
            slow = max(lingered, key=lambda z: z['dwell_s'])
            sentences.append('people linger longest around %s, at about %ss at a time'
                             % (slow['label'], _fmt(slow['dwell_s'])))

        # the single most useful next step, stated plainly
        if cues:
            cue = cues[0]
            ev = cue.get('evidence') or {}
            action = ('%s has stayed at or above its review limit for %ss, so that is the one place '
                      'worth walking over to' % (cue.get('zone_label') or cue.get('zone'),
                                                  _fmt(ev.get('duration_s'))))
            if len(cues) > 1:
                action += ', and there %s %d more flagged' % ('is' if len(cues) == 2 else 'are', len(cues) - 1)
        else:
            action = 'Nothing needs your attention right now, so you can leave it be'
        sentences.append(action)
        spoken = [(x[0].upper() + x[1:]) if x else x for x in sentences]
        return '. '.join(spoken).rstrip('.') + '.'

    @staticmethod
    def _compose_bottleneck(zones, cues, store=None):
        store = store or {'has_layout': False, 'sections': [], 'cues': []}
        if store['has_layout'] and store['cues']:
            out = []
            for cue in store['cues'][:3]:
                if cue['kind'] == 'redistribution_candidate':
                    busy = next((s['name'] for s in store['sections'] if s['id'] == cue['section_id']), cue['section_id'])
                    alt = next((s['name'] for s in store['sections'] if s['id'] == cue['candidate_id']), cue['candidate_id'])
                    out.append('%s is carrying sustained activity while %s has been quiet, so moving a '
                               'display or activity from the first to the second is worth trialling' % (busy, alt))
                elif cue['kind'] == 'inspection':
                    name = next((s['name'] for s in store['sections'] if s['id'] == cue['section_id']), cue['section_id'])
                    out.append('%s has been busy enough to hold a sustained cue, so check access and aisle '
                               'clearance there' % name)
                elif cue['kind'] == 'topology_watch':
                    out.append(cue['title'] + ', which sits on several computed walking routes')
            return ('Across the whole floor, ' + '; '.join(out) +
                    '. These are suggestions to check against the shop, not causes I have proven.')
        return Assistant._compose_zone_bottleneck(zones, cues)

    @staticmethod
    def _compose_section_dwell(sections):
        scored = [s for s in sections if s.get('partial_dwell_s') and s.get('observed_tracks')]
        if not scored:
            return ('No dwell has been recorded on the drawn sections yet. '
                    'Dwell is time actually seen between two sightings, so it needs a little movement first.')
        best = max(scored, key=lambda s: s['partial_dwell_s'])
        rest = sorted(scored, key=lambda s: s['partial_dwell_s'], reverse=True)[1:3]
        text = ('Across the drawn sections, people spend the longest around %s, at about %ss each time'
                % (best['name'], _fmt(best['partial_dwell_s'])))
        if rest:
            text += ', then %s' % ', '.join('%s at %ss' % (s['name'], _fmt(s['partial_dwell_s'])) for s in rest)
        return (text + '. That is time the cameras actually saw someone, so anyone who walked behind a '
                      'fixture contributes less than they really were there.')

    @staticmethod
    def _compose_zone_bottleneck(zones, cues):
        """Rank zones by sustained observed pressure, never by model opinion.

        A zone counts as a bottleneck only when it carries a sustained cue from
        insights.sustained_pressure, which already requires contiguity, a minimum
        duration and a minimum number of supporting samples. Brief spikes therefore
        cannot become "bottlenecks" by being the largest number in the frame.
        """
        ranked = []
        for cue in cues or []:
            ev = cue.get('evidence') or {}
            duration = float(ev.get('duration_s') or 0)
            ranked.append((duration, float(ev.get('peak_observed') or ev.get('minimum_observed') or 0),
                           cue.get('zone_label') or cue.get('zone'), ev))
        ranked.sort(reverse=True)
        if not ranked:
            busy = busiest(zones)
            if busy is None:
                return ('No zone has been observed long enough to judge congestion. '
                        'Start a camera and let it run for a minute or two.')
            if busy.get('occupancy') is None:
                return ('No sustained congestion is flagged, and there is no current count to rank: '
                        'the last processed frame is stale. Restart the camera to resume measuring.')
            return ('No sustained congestion is flagged in this camera right now. '
                    'The busiest zone is %s at %s observed people, which is below its review threshold '
                    'or not sustained long enough to qualify.'
                    % (busy['label'], busy.get('occupancy')))
        parts = []
        for duration, peak, label, ev in ranked[:3]:
            shape = ('sustained blockage' if duration >= 15 else
                     'moderate standing congestion' if duration >= 8 else 'brief spike')
            parts.append('%s is the highest pressure zone: %s people observed over %ss (%s)'
                         % (label, peak, duration, shape))
        tail = (' Bottleneck wording describes observed occupancy only; it is not proof of a queue, '
                'blocked exit or lost sale.')
        return 'Ranked by sustained observed pressure. ' + '. '.join(parts) + '.' + tail

    @staticmethod
    def _compose_dead(zones, store=None):
        """Zones with no observed entries and near-zero occupancy, phrased as a cue to check.

        With a floor plan drawn, the stricter layout rule is used: a section only counts
        when it was actually measured, stayed at or below half a person on average, and is
        not already flagged. An area we have never measured is not a dead zone.
        """
        store = store or {'has_layout': False, 'sections': [], 'cues': []}
        if store.get('has_layout') and store.get('sections'):
            quiet = Assistant._underused(store['sections'])
            if not quiet:
                return ('No dead zones. Every section that has been measured has seen someone, and no '
                        'unmeasured area is being called dead on the strength of having no data.')
            listed = ', '.join('%s (average %s people over %s samples)'
                               % (s['name'], _fmt(s['mean_5m'], 2), s['samples_5m']) for s in quiet[:4])
            return ('Quiet areas worth a look: %s. Quiet means measured and barely used, not proven '
                    'unused, so walk over before you change anything.' % listed)
        if not zones:
            return 'There are no configured zones to evaluate yet.'
        dead = [z for z in zones
                if (z.get('entries') in (0, None) and (z.get('peak') in (0, None))
                    and (z.get('mean_5m') in (0, None) or z.get('mean_5m') == 0))]
        if not dead:
            return ('No dead zones detected. Every configured zone has recorded at least one '
                    'observed track entry in this camera.')
        listed = ', '.join('%s (%s observed entries, peak %s)'
                           % (z['label'], z.get('entries'), z.get('peak')) for z in dead[:4])
        tail = (' Empty here means no visible track entries in this camera only, which can also mean '
                'the camera cannot see that floor area or is blocked. It is not proof the space is unused.')
        return 'Possible dead zones to check: %s.%s' % (listed, tail)

    def compose_metric(self, question, p):
        zones, health, intent = p['zones'], p['measurement'], p['intent']
        lead = '' if health['reliable'] else health['text'] + '. '
        top = busiest(zones)
        cues = p.get('cues') or []

        if intent == 'health':
            return lead + health['text'] + '.'

        store = p.get('store') or {'has_layout': False, 'sections': [], 'cues': []}

        if intent == 'bottleneck':
            return lead + self._compose_bottleneck(zones, cues, store)

        if intent == 'dead':
            return lead + self._compose_dead(zones, store)

        if intent == 'dwell' and store['has_layout']:
            return lead + self._compose_section_dwell(store['sections'])

        if intent == 'cues':
            if not cues:
                return lead + 'No review cues are active for this camera right now.'
            lines = []
            for cue in cues[:3]:
                ev = cue.get('evidence', {})
                lines.append('%s: %s (at least %s people observed across %s samples spanning %ss)'
                             % (cue.get('zone_label') or cue.get('zone'),
                                cue.get('message', ''),
                                ev.get('minimum_observed'), ev.get('support_samples'),
                                ev.get('duration_s')))
            return lead + 'Active review cues. ' + ' '.join(lines) + ' These are observations to check, not proven events.'

        if intent == 'dwell':
            scored = [z for z in zones if z.get('dwell_tracks')]
            if not scored:
                return lead + 'No partial visible dwell has been recorded for this camera yet.'
            target = self._zone_in_question(question, zones)
            scored = [z for z in scored if not target or z['zone'] == target] or scored
            best = max(scored, key=lambda z: z['dwell_s'])
            parts = ['%s %ss mean partial visible dwell across %s partial track-zone segments.'
                     % (best['label'], _fmt(best['dwell_s']), best['dwell_tracks'])]
            parts.append('Partial dwell covers only observed intervals between consecutive reliable sightings; '
                         'unknown time and blind gaps are excluded.')
            return lead + ' '.join(parts)

        if intent == 'entries':
            scored = [z for z in zones if z.get('entries')]
            if not scored:
                return lead + 'No track entries have been recorded yet.'
            best = max(scored, key=lambda z: z['entries'])
            return lead + ('%s shows %s observed track entries, the most of any zone. These are camera-local '
                           'track identifiers, not distinct people, and a fragmented track can count more than once.'
                           % (best['label'], best['entries']))

        if intent == 'trends':
            trend = p.get('trend')
            if not trend:
                return lead + 'There is not enough observation history yet to show a trend.'
            label = next((z['label'] for z in zones if z.get('zone') == trend.get('zone')), trend['zone'])
            return lead + ('Over the last %ss, %s peaked at %s observed people with a mean of %s across %s samples.'
                           % (_fmt(trend['window_s']), label, _fmt(trend['peak']), _fmt(trend['mean'], 2), trend['samples']))

        if intent == 'summary':
            return lead + self._compose_story(zones, cues, p.get('trend'))

        # occupancy
        target = self._zone_in_question(question, zones)
        chosen = next((z for z in zones if z['zone'] == target), None)
        if chosen:
            return lead + ('%s currently shows %s observed people, peak %s, ninety percent occupancy over five '
                           'minutes %s.' % (chosen['label'], _fmt(chosen['occupancy']), _fmt(chosen['peak']),
                                            _fmt(chosen['p90'])))
        if not zones:
            return lead + 'This camera has no floor zones configured, so there is no section data to report.'
        parts = []
        for z in zones:
            parts.append('%s %s now, peak %s' % (z['label'], _fmt(z['occupancy']), _fmt(z['peak'])))
        return lead + 'Observed occupancy by zone. ' + '; '.join(parts) + '.'

    # ---- spoken composition ------------------------------------------------
    def compose_spoken(self, question, p):
        """Short, conversational, answer-first. Used for voice output.

        This is the path that actually runs without a local model, so it carries the same
        spoken contract the model is given: answer first, at most one or two headline
        numbers, a caveat only when it changes trust, and a hook that invites a follow-up.
        """
        zones = p.get('zones') or []
        cues = p.get('cues') or []
        health = p.get('measurement') or {}
        intent = p.get('intent')
        top = busiest(zones)
        trust = '' if health.get('reliable') else 'Heads up, the data is stale, so take this with a grain of salt. '

        if intent == 'bottleneck':
            if cues:
                cue = cues[0]
                ev = cue.get('evidence') or {}
                label = cue.get('zone_label') or cue.get('zone')
                return ('%sOne thing worth checking: %s has held steady above its threshold for %s. %s'
                        % (trust, label, say_seconds(ev.get('duration_s')),
                           'Want me to keep watching it?'))
            if top and top.get('occupancy') is not None:
                return ('%sNothing is blocked right now. %s is the busiest at %s, but it has not stayed high '
                        'long enough to call it a bottleneck. Want me to keep an eye on it?'
                        % (trust, top['label'], say_people(top['occupancy'])))
            return '%sI cannot judge congestion yet. Start a camera and give it a minute. ' % trust

        if intent == 'dead':
            quiet = [z for z in zones if not z.get('entries') and not z.get('peak')]
            if not quiet:
                return ('%sNo dead zones. Every zone I can see has had someone in it. Want the count per zone?'
                        % trust)
            return ('%s%s looks empty right now. That can also mean my view of that floor is blocked. '
                    'Want me to check it again in a minute?' % (trust, quiet[0]['label']))

        if intent == 'cues':
            if not cues:
                return '%sNothing needs your attention right now. Want the busiest zone instead?' % trust
            cue = cues[0]
            return ('%sOne thing to check: %s. %s' % (trust, cue.get('message', 'a zone needs a look'),
                                                     'Want details?'))

        if intent == 'dwell':
            scored = [z for z in zones if z.get('dwell_tracks')]
            if not scored:
                return '%sI have not seen enough movement yet to estimate dwell. ' % trust
            target = self._zone_in_question(question, zones)
            scored = [z for z in scored if not target or z['zone'] == target] or scored
            best = max(scored, key=lambda z: z['dwell_s'])
            return ('%sPeople linger longest in %s, around %s. That is time actually seen, so a hidden '
                    'stretch would not be counted. Want the per-zone comparison?'
                    % (trust, best['label'], say_seconds(best['dwell_s'])))

        if intent == 'entries':
            scored = [z for z in zones if z.get('entries')]
            if not scored:
                return '%sNo movement recorded yet. ' % trust
            best = max(scored, key=lambda z: z['entries'])
            return ('%s%s has seen the most traffic, with %s entries. That counts track identifiers, not '
                    'distinct people. Want the busiest area right now?'
                    % (trust, best['label'], say_count(best['entries'])))

        if intent == 'health':
            return ('%s%s Want me to look at any particular zone?' % (trust, health.get('text', 'Data looks healthy')))

        if intent == 'trends':
            trend = p.get('trend')
            if not trend:
                return '%sI need a bit more history before I can show a trend. ' % trust
            label = next((z['label'] for z in zones if z.get('zone') == trend.get('zone')), trend['zone'])
            return ('%s%s has averaged %s people and peaked at %s. Want me to keep watching it?'
                    % (trust, label, say_count(round(trend['mean'])), say_count(trend['peak'])))

        if intent == 'summary':
            if not top:
                return '%sNothing to report yet. Start a camera and I will watch it for you. ' % trust
            if cues:
                cue = cues[0]
                return ('%sThe busiest spot is %s with %s, and %s has been over its review limit for %s. '
                        'That is the one I would walk over to. Want me to keep watching?'
                        % (trust, top['label'], say_people(top['occupancy'] or 0),
                           cue.get('zone_label') or cue.get('zone'),
                           say_seconds((cue.get('evidence') or {}).get('duration_s'))))
            return ('%s%s is the busiest spot with %s, %s. Nothing needs your attention right now. '
                    'Want me to check anything else?'
                    % (trust, top['label'], say_people(top['occupancy'] or 0),
                       'comfortably under your review limit' if top.get('threshold') and
                       (top.get('occupancy') or 0) < top['threshold'] else 'still under its review limit'))

        # occupancy
        target = self._zone_in_question(question, zones)
        chosen = next((z for z in zones if z['zone'] == target), None)
        if chosen:
            return ('%s%s has %s right now, %s, and it has peaked at %s. %s'
                    % (trust, chosen['label'], say_people(chosen['occupancy'] or 0),
                       spoken_meaning(chosen), say_people(chosen['peak'] or 0),
                       'Want me to keep an eye on it?'))
        if not top:
            return '%sThere is nothing moving in view right now. ' % trust
        return ('%sThe busiest spot is %s with %s, %s. %s'
                % (trust, top['label'], say_people(top['occupancy'] or 0),
                   spoken_meaning(top), 'Want a per-zone breakdown?'))

    def compose_doc(self, question, p):
        docs = p.get('definitions') or []
        if not docs:
            return ('I do not have a project document that covers that. I can answer status questions about the '
                    'observed zones, or explain what the documented metrics and limitations mean.')
        # prefer a chunk that actually reads as prose; the corpus is engineering-grade
        readable = [(d, _plain(d['text'], question)) for d in docs]
        readable = [(d, t) for d, t in readable if len(t.split()) >= 8]
        if not readable:
            return ('The project notes cover that, but only in engineering terms I would not read aloud. '
                    'I can still tell you what the cameras are seeing right now.')
        doc, text = readable[0]
        return '%s (From %s.)' % (text, doc['source'].split('/')[-1])