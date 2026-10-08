"""Evidence-gated, non-causal operational cues for store operators.

These are transparent heuristics, not trained bottleneck or queue classifiers.
All times are monotonic capture/processing-clock seconds for one camera only.
"""

ZONE_ROLES = {'checkout', 'aisle', 'display', 'entrance', 'other'}

ROLE_ACTIONS = {
    'checkout': 'Check whether checkout staffing or lane access needs attention.',
    'aisle': 'Check aisle clearance and whether restocking obstructs movement.',
    'display': 'Check display accessibility; browsing may explain the gathering.',
    'entrance': 'Check entrance clearance and pedestrian flow.',
    'other': 'Review this area on video before deciding whether action is needed.',
}


def sustained_pressure(samples, threshold, persistence_s=5.0, min_samples=4,
                       max_gap_s=3.0, slow_threshold=0.6):
    """Return transparent evidence only for contiguous above-threshold samples.

    `samples` must be in time order, with capture-time `time` and `count`.
    Brief spikes and large gaps must not trigger a staffing/flow cue.
    """
    if not samples or threshold < 1:
        return None
    segment = []
    for item in reversed(samples):
        if item['count'] < threshold:
            break
        if segment and segment[-1]['time'] - item['time'] > max_gap_s:
            break
        segment.append(item)
    segment.reverse()
    if len(segment) < min_samples:
        return None
    duration = segment[-1]['time'] - segment[0]['time']
    if duration < persistence_s:
        return None
    speed_values = [s['slow_fraction'] for s in segment if s.get('slow_fraction') is not None]
    fraction_slow = (sum(x >= slow_threshold for x in speed_values) / len(speed_values)
                     if speed_values else None)
    return {'duration_s': round(duration, 1), 'support_samples': len(segment),
            'minimum_observed': min(s['count'] for s in segment),
            'peak_observed': max(s['count'] for s in segment),
            'slow_support_samples': len(speed_values),
            'slow_majority': len(speed_values) >= min_samples and fraction_slow >= 0.6}


def make_recommendation(zone, evidence):
    if evidence is None:
        return None
    role = zone.get('role', 'other')
    if role not in ZONE_ROLES:
        role = 'other'
    return {
        'zone': zone['id'], 'zone_label': zone.get('label', zone['id']),
        'zone_role': role, 'kind': 'sustained_observed_occupancy',
        'severity': 'review',
        'message': ROLE_ACTIONS[role],
        'reason': (f"At least {evidence['minimum_observed']} people observed across "
                   f"{evidence['support_samples']} samples spanning "
                   f"{evidence['duration_s']}s in this camera."),
        'evidence': evidence,
        'note': 'Observation only. Not proof of queue, lost sales or unique people.',
    }
