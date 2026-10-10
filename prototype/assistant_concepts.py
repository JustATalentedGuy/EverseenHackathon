"""Canonical plain-English definitions for the concepts operators actually ask about.

The research notes state these correctly but in notation (`persistence = duration
C_k(t) > threshold`), which is useless read aloud, and the dead-zone rule exists only in
code. These entries restate the same definitions in speech, each carrying the source it
came from so an answer can still be traced.

Nothing here invents a definition. Each one is a faithful restatement of the cited text
or of the rule implemented in topology.insights.
"""

CONCEPTS = {
    'occupancy': {
        'terms': ['occupancy', 'how many people', 'people right now', 'crowded', 'busiest'],
        'answer': ('Occupancy is how many tracked people the camera can see standing inside a zone right now. '
                   'It counts a person by their feet, not the middle of a detection box, so someone standing '
                   'just outside the zone does not count.'),
        'source': 'prototype/INTEGRATION.md',
    },
    'dwell': {
        'terms': ['dwell', 'how long do people stay', 'linger', 'lingering', 'how long stay',
                  'time spent', 'sticky'],
        'answer': ('Dwell is how long someone spends inside a zone. We only measure the stretches the camera '
                   'can actually see them, so the clock pauses whenever they walk behind a shelf or a fixture '
                   'and it is never a guess at their total visit. It is reported as an average across '
                   'track-and-zone segments, not one whole visit.'),
        'source': 'research/METRICS_AND_BOTTLENECK_SIGNALS.md',
    },
    'bottleneck': {
        'terms': ['bottleneck', 'congestion', 'congested', 'blocked', 'jammed', 'gridlock',
                  'chokepoint', 'choke point'],
        'answer': ('A bottleneck is a zone that stays at or above the review limit you set for it, continuously, '
                   'for long enough to matter. A quick spike of people does not count, because that is normal '
                   'and nothing has actually been held up. The harder a zone stays full and the longer it '
                   'stays full, the higher it is ranked.'),
        'source': 'prototype/INTEGRATION.md',
    },
    'dead_zone': {
        'terms': ['dead zone', 'dead zone', 'deadzones', 'dead spot', 'underused', 'under used',
                  'unused', 'deserted', 'idle area', 'never used', 'quiet area'],
        'answer': ('A dead zone is an area that the cameras can see properly, that we have measured, and that has '
                   'averaged almost nobody in it — half a person or less — with nothing flagged on it. An area we '
                   'have not managed to measure is never called a dead zone, because quiet and unwatched are not '
                   'the same thing.'),
        'source': 'prototype/topology.py (insights)',
    },
    'track_entries': {
        'terms': ['track entries', 'track entry', 'entries', 'how many times', 'track ids'],
        'answer': ('Track entries count how many camera-local tracks passed through a zone. If the tracker loses '
                   'someone behind a shelf and picks them up again, that can count twice, so it measures activity '
                   'rather than distinct people.'),
        'source': 'prototype/INTEGRATION.md',
    },
    'review_cue': {
        'terms': ['review cue', 'alert', 'warning', 'flag', 'recommendation', 'what needs attention'],
        'answer': ('A review cue fires when a zone stays at or above the limit you set for it, across repeated '
                   'readings, rather than spiking once. Each cue comes with the smallest count seen, how long it '
                   'lasted and how many readings backed it up, so you can judge it yourself.'),
        'source': 'prototype/INTEGRATION.md',
    },
    'heatmap': {
        'terms': ['heatmap', 'heat map', 'where did people go', 'hot spot', 'hotspot'],
        'answer': ('The heatmap is where people were seen, not how many different people passed. Each square shows '
                   'the average number of tracked people standing in it over the period you pick, so a square that '
                   'stays faintly warm means someone was usually there, while a bright flash just means a lot of '
                   'people crossed it briefly.'),
        'source': 'prototype/HEATMAP.md',
    },
}


def lookup(question):
    """Return (answer, source, concept) when the question asks about a known concept."""
    text = (question or '').lower()
    best = None
    for name, entry in CONCEPTS.items():
        for term in entry['terms']:
            if term in text:
                # prefer the longest matching phrase, i.e. the most specific
                if best is None or len(term) > len(best[1]):
                    best = (entry, term, name)
    if best is None:
        return None
    entry, _, name = best
    return entry['answer'], entry['source'], name


def is_asking_for_definition(question):
    """True when the shopkeeper wants to know what a word means, not what it says now."""
    lowered = (question or '').lower()
    markers = ('what does', 'what is', 'whats', 'what are', 'meaning', 'mean', 'define',
               'definition', 'explain', 'stands for', 'counts as', 'count as')
    return any(marker in lowered for marker in markers)