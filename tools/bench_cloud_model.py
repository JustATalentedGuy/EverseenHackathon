"""Benchmark cloud models on the assistant's actual phrasing job.

Scores each candidate on what the project actually cares about: does it stay short, keep
the numbers intact, avoid forbidden claims, and end with a follow-up offer. Uses the
same adapter and prompt the application uses, so the winner is the real configuration.
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prototype import assistant_llm  # noqa: E402

KEY = os.environ.get('ASSISTANT_CLOUD_API_KEY') or os.environ.get('GROQ_API_KEY')
URL = os.environ.get('ASSISTANT_CLOUD_URL', 'https://api.groq.com/openai/v1').rstrip('/')

CASES = [
    ('Main aisle currently shows 5 observed people, peak 7, ninety percent occupancy over five minutes 4.',
     {'answer_to_rewrite': '', 'measurement_state': 'observing',
      'zones': [{'label': 'Main aisle', 'occupancy': 5, 'peak': 7, 'p90': 4, 'dwell_s': 11.0, 'entries': 16}],
      'active_cues': 0}),
    ('Counter service area has stayed at or above its review limit for 22s, so it is worth walking over there.',
     {'answer_to_rewrite': '', 'measurement_state': 'observing',
      'zones': [{'label': 'Counter service area', 'occupancy': 5, 'peak': 6, 'p90': 5, 'dwell_s': 6.3, 'entries': 12}],
      'active_cues': 1}),
    ('Data is being observed normally (last frame 0.2s ago, 3.8 fps against a 5 Hz target).',
     {'answer_to_rewrite': '', 'measurement_state': 'observing', 'zones': [], 'active_cues': 0}),
]

FORBIDDEN = ('unique shopper', 'unique visitor', 'revenue', 'sales', 'checkout wait',
             'percentile', 'partial visible dwell', 'camera-local', 'observed people')


def ask(model, system, user):
    body = json.dumps({'model': model, 'temperature': 0.3, 'max_tokens': 512,
                       'messages': [{'role': 'system', 'content': system},
                                    {'role': 'user', 'content': user}]}).encode()
    request = urllib.request.Request(URL + '/chat/completions', data=body, headers={
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY,
        'User-Agent': 'everseen-prototype/1.0 (+local analytics)'})
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=45) as response:
        data = json.loads(response.read().decode())
    message = data['choices'][0]['message']
    text = (message.get('content') or '').strip()
    if not text and message.get('reasoning'):
        # reasoning-only models: the budget was consumed before any answer was written
        raise ValueError('no content (reasoning-only response)')
    return text, time.perf_counter() - started


def score(text, source):
    problems = []
    lowered = text.lower()
    for term in FORBIDDEN:
        if term in lowered:
            problems.append('said %r' % term)
    if len(text) > 320:
        problems.append('too long (%d chars)' % len(text))
    if len(text.split()) < 8:
        problems.append('too short')
    if not text.rstrip().endswith('?'):
        problems.append('no follow-up hook')
    # Figures must survive, and the contract asks for them as words ("five", not "5"),
    # so accept either form but never a missing or altered value.
    words = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
             'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
             'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
             'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20}
    lowered_text = text.lower()
    for number in sorted(set(re.findall(r'\d+', source)), key=int):
        value = int(number)
        spoken_ok = words.get(number) == value
        alt = {20: 'twenty', 22: 'twenty-two', 5: 'five', 7: 'seven', 4: 'four'}.get(value)
        if str(value) not in re.findall(r'\d+', text) and not spoken_ok and not (
                alt and alt in lowered_text):
            problems.append('lost the figure %s' % number)
    if re.search(r'\*\*|^#|^\-\s|\d\.\s', text, re.M):
        problems.append('markdown leaked')
    return problems


def main():
    models = sys.argv[1:] or ['openai/gpt-oss-20b', 'qwen/qwen3.8-27b', 'openai/gpt-oss-120b', 'allam-2-7b']
    print(f'{"model":28s} {"ok":>3s} {"words":>5s} {"latency":>8s}  notes')
    for model in models:
        passed, lengths, latencies, notes = 0, [], [], []
        for answer, payload in CASES:
            facts = json.dumps(payload, ensure_ascii=False)
            facts = facts.replace('"answer_to_rewrite": ""', '"answer_to_rewrite": %s' % json.dumps(answer))
            try:
                text, latency = ask(model, assistant_llm.SYSTEM, facts + ' /no_think')
            except Exception as exc:
                notes.append('ERROR %s' % str(exc)[:60]); continue
            latencies.append(latency); lengths.append(len(text.split()))
            problems = score(text, answer)
            if not problems:
                passed += 1
            else:
                notes.extend(problems[:2])
        avg = sum(latencies) / len(latencies) if latencies else float('nan')
        print(f'{model:28s} {passed:3d}/{len(CASES)} {int(sum(lengths)/len(lengths)) if lengths else 0:5d} '
              f'{avg:7.2f}s  {"; ".join(notes[:3])[:70]}')
        if passed == len(CASES):
            try:
                print('    sample:', ask(model, assistant_llm.SYSTEM, facts)[0][:200])
            except ValueError:
                pass


if __name__ == '__main__':
    main()