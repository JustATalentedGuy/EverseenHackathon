"""Render the current system state as a retrievable document.

The static corpus explains what the metrics mean. This module describes what the metrics
currently say, in the same chunked format, so one BM25 search can retrieve both the rule
and the present fact. It is regenerated per question because the store changes constantly;
nothing here is cached or written to disk.
"""
from __future__ import annotations

LIVE = 'system: live observations'
SECTIONS = 'system: drawn floor sections'
CUES = 'system: active review cues'
TOPOLOGY = 'system: floor topology insights'


def _fmt(value, digits=1):
    if value is None:
        return 'n/a'
    return ('%.' + str(digits) + 'f') % float(value)


def render(assistant):
    """Build the dynamic document for the assistant's current state."""
    sections_out = []

    try:
        stats_by_camera = {}
        for camera_id in assistant._cameras():
            camera = assistant.live.get(camera_id)
            if camera is None:
                continue
            stats = camera.stats()
            if stats:
                stats_by_camera[camera_id] = stats
    except Exception:
        stats_by_camera = {}

    for camera_id, stats in stats_by_camera.items():
        health = stats.get('measurement', {})
        lines = ['### %s' % (stats.get('name') or camera_id),
                 'measurement state: %s, frames analysed: %s, sampling rate %s fps against a %s target'
                 % (health.get('state', 'unknown'), stats.get('frames', 0),
                    _fmt(health.get('observed_fps_30s'), 1), _fmt(health.get('target_hz'), 1))]
        for zone in stats.get('zones', []):
            lines.append(
                '- zone %s (role %s, review limit %s): occupancy now %s, peak %s, ninety percent of the '
                'last five minutes %s, mean over five minutes %s, observed track entries %s, '
                'partial dwell mean %ss across %s partial segments'
                % (zone.get('label') or zone.get('id'), zone.get('role', 'other'),
                   zone.get('crowd_threshold'), zone.get('occupancy'), zone.get('peak'),
                   _fmt(zone.get('p90_occupancy_5m'), 1), _fmt(zone.get('mean_occupancy_5m'), 2),
                   zone.get('observed_track_entries'), _fmt(zone.get('partial_dwell_mean_s')),
                   zone.get('partial_dwell_tracks')))
        for cue in stats.get('inspection_cues', []):
            evidence = cue.get('evidence', {})
            lines.append('- review cue for %s: %s. At least %s people observed across %s samples '
                         'spanning %ss.'
                         % (cue.get('zone_label') or cue.get('zone'), cue.get('message', ''),
                            evidence.get('minimum_observed'), evidence.get('support_samples'),
                            evidence.get('duration_s')))
        sections_out.append((LIVE, '\n'.join(lines)))

    try:
        store = assistant.store()
    except Exception:
        store = {'has_layout': False, 'sections': [], 'cues': []}

    if store.get('has_layout') and store.get('sections'):
        lines = ['### Sections currently mapped to the drawn floor plan']
        for section in store['sections']:
            lines.append(
                '- %s (role %s): observed people now %s, five minute mean %s, ninety percent %s, '
                'partial dwell mean %ss, observed tracks %s, %s samples, state %s'
                % (section.get('name'), section.get('role', 'other'), section.get('count'),
                   _fmt(section.get('mean_5m'), 2), _fmt(section.get('p90_5m'), 1),
                   _fmt(section.get('partial_dwell_s')), section.get('observed_tracks'),
                   section.get('samples_5m'), section.get('state')))
        underused = assistant._underused(store['sections'])
        if underused:
            lines.append('Sections measured and quiet right now: %s.'
                         % ', '.join(s['name'] for s in underused))
        else:
            lines.append('No section is both measured and quiet right now.')
        sections_out.append((SECTIONS, '\n'.join(lines)))

        if store.get('cues'):
            lines = ['### Floor-level hypotheses derived from the current observations']
            for cue in store['cues']:
                lines.append('- %s. %s Evidence: %s. Caveat: %s'
                             % (cue.get('title', ''), cue.get('recommendation', ''),
                                cue.get('evidence', ''), cue.get('caveat', '')))
            sections_out.append((TOPOLOGY, '\n'.join(lines)))

    return sections_out