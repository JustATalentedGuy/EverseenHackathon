"""Ingest analytics results into the retrieval corpus.

The detector and tracker already do the video work. This module takes what they produced
and writes it into the same document store the assistant reads, so answering a question
means retrieving from the corpus rather than reaching into the video feed. The corpus is
plain Markdown under runs/assistant/knowledge, so it can be inspected, corrected or
deleted by hand, and every answer carries the timestamp of the snapshot it came from.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / 'runs' / 'assistant' / 'knowledge'
LATEST = KNOWLEDGE / 'latest'


def _stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _fmt(value, digits=1):
    if value is None:
        return 'not measured'
    return ('%.' + str(digits) + 'f') % float(value)


def render_cameras(status):
    """One section per running camera: occupancy, dwell and track activity."""
    lines = ['# Live camera observations',
             '',
             'These are the numbers the detector and tracker produced from the video. '
             'Occupancy counts tracked people whose feet were inside a zone; dwell is time '
             'between two reliable sightings, so it undercounts anyone hidden behind a fixture.',
             '']
    written = False
    for camera in status.get('cameras', []):
        health = camera.get('measurement', {})
        lines.append('## %s' % (camera.get('name') or camera.get('id')))
        lines.append('State: %s. Frames processed: %s. Sampling %.1f fps against a %.0f target.'
                     % (health.get('state', 'unknown'), camera.get('frames', 0),
                        float(health.get('observed_fps_30s') or 0), float(health.get('target_hz') or 0)))
        for zone in camera.get('zones', []):
            lines.append('- **%s** (role %s, review limit %s): now %s, peak %s, ninety percent over '
                         'five minutes %s, five-minute mean %s, observed track entries %s, '
                         'partial dwell mean %ss across %s partial segments'
                         % (zone.get('label') or zone.get('id'), zone.get('role', 'other'),
                            zone.get('crowd_threshold'), zone.get('occupancy'), zone.get('peak'),
                            _fmt(zone.get('p90_occupancy_5m')), _fmt(zone.get('mean_occupancy_5m'), 2),
                            zone.get('observed_track_entries'), _fmt(zone.get('partial_dwell_mean_s')),
                            zone.get('partial_dwell_tracks')))
        for cue in camera.get('inspection_cues', []):
            evidence = cue.get('evidence', {})
            lines.append('- Review cue on %s: %s. At least %s people across %s samples spanning %ss.'
                         % (cue.get('zone_label') or cue.get('zone'), cue.get('message', ''),
                            evidence.get('minimum_observed'), evidence.get('support_samples'),
                            evidence.get('duration_s')))
        if not camera.get('zones'):
            lines.append('- No floor zones are configured for this camera yet.')
        lines.append('')
        written = True
    return '\n'.join(lines) if written else ''


def render_layout(report):
    """Store-wide sections, dwell and the topology hypotheses derived from them."""
    sections = report.get('sections') or []
    if not sections:
        return ''
    lines = ['# Whole-floor sections',
             '',
             'Sections are the operator-drawn map of the shop, each linked to one or more camera '
             'zones. Counts take the maximum across linked cameras rather than a sum, because the '
             'cameras are not synchronized.', '']
    for section in sections:
        lines.append('## %s (%s)' % (section.get('name'), section.get('role', 'other')))
        dwell = section.get('partial_dwell_s')
        lines.append('People now: %s. Five-minute mean %s. Partial dwell mean %s over %s observed '
                     'tracks. %s samples. State: %s.'
                     % (section.get('count'), _fmt(section.get('mean_5m'), 2),
                        ('not measured' if dwell is None else '%s seconds' % _fmt(dwell)),
                        section.get('observed_tracks') if section.get('observed_tracks') is not None
                        else 'no', section.get('samples_5m'), section.get('state')))
        for evidence in section.get('review_evidence') or []:
            lines.append('- Has a sustained review cue: %s' % evidence.get('message', ''))
        lines.append('')
    insights = report.get('insights') or []
    if insights:
        lines += ['# Whole-floor observations to check', '']
        for cue in insights:
            lines.append('## %s' % cue.get('title', 'Observation'))
            lines.append(cue.get('recommendation', ''))
            lines.append('Evidence: %s' % cue.get('evidence', ''))
            lines.append('Caveat: %s' % cue.get('caveat', ''))
            lines.append('')
    return '\n'.join(lines)


def render_history():
    """Previous batch runs, so questions about earlier footage can be answered."""
    runs = ROOT / 'experiments' / 'deadline'
    if not runs.exists():
        return ''
    blocks = []
    for summary_path in sorted(runs.glob('*/summary.json')):
        try:
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        cameras = summary.get('cameras') or {}
        lines = ['# Recorded footage analysis (%s)' % summary_path.parent.name,
                 'Frames processed: %s. Wall time: %ss.' % (summary.get('camera_samples'),
                                                           round(float(summary.get('wall_seconds') or 0))),
                 '']
        for camera_id, camera in cameras.items():
            dwell = camera.get('observed_dwell') or []
            per_zone = {}
            for entry in dwell:
                per_zone.setdefault(entry['zone'], []).append(float(entry.get('seconds') or 0))
            lines.append('## %s' % camera_id)
            for zone, values in sorted(per_zone.items()):
                lines.append('- %s: %s partial dwell segments, mean %ss, longest %ss'
                             % (zone, len(values), round(sum(values) / len(values), 1), round(max(values), 1)))
            if not per_zone:
                lines.append('- No dwell segments were recorded in this run.')
            lines.append('')
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def ingest(status=None, report=None):
    """Write the current analytics into the corpus. Returns the files written."""
    KNOWLEDGE.mkdir(parents=True, exist_ok=True)
    generated = _stamp()
    documents = {}
    if status:
        text = render_cameras(status)
        if text:
            documents['live-observations.md'] = text
    if report:
        text = render_layout(report)
        if text:
            documents['whole-floor-sections.md'] = text
    history = render_history()
    if history:
        documents['recorded-footage-history.md'] = history

    manifest = {'generated_at': generated, 'documents': sorted(documents)}
    (KNOWLEDGE / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for name, text in documents.items():
        header = '<!-- generated %s by prototype/assistant_ingest.py; edit the source, not this file -->\n' % generated
        (KNOWLEDGE / name).write_text(header + text, encoding='utf-8')
    for stale in KNOWLEDGE.glob('*.md'):
        if stale.name not in documents:
            stale.unlink()
    return manifest


def knowledge_dir():
    return KNOWLEDGE if KNOWLEDGE.exists() else None


def latest_stamp():
    manifest = KNOWLEDGE / 'manifest.json'
    if not manifest.exists():
        return None
    try:
        return json.loads(manifest.read_text(encoding='utf-8')).get('generated_at')
    except Exception:
        return None