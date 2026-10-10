"""Periodic store briefing plus a free WhatsApp delivery path.

Delivery is intentionally zero-cost and zero-account: WhatsApp's official
click-to-chat link (`wa.me`) carries the pre-filled message, with a clipboard
fallback. The scheduling loop is one asyncio task so no new dependency and no
extra process is required.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from . import assistant

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'prototype' / 'assistant_config.json'
LOG = ROOT / 'runs' / 'assistant' / 'deliveries.jsonl'

FREQUENCIES = [15, 30, 60, 120, 240, 1440]      # minutes
E164 = r'^\+[1-9]\d{6,14}$'


def default_config():
    return {'recipients': [], 'frequency_minutes': 60, 'paused': False,
            'whatsapp_mode': 'deep_link', 'last_sent_at': None, 'next_due_at': None}


def load_config():
    if CONFIG.exists():
        try:
            data = json.loads(CONFIG.read_text(encoding='utf-8'))
            base = default_config()
            base.update({k: v for k, v in data.items() if k in base})
            return base
        except (json.JSONDecodeError, OSError):
            pass
    return default_config()


def save_config(config):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(config, indent=1), encoding='utf-8')


def validate_recipient(entry):
    name = str(entry.get('name', '')).strip()[:60]
    raw = str(entry.get('number', '')).strip().replace(' ', '').replace('-', '')
    if raw and not raw.startswith('+'):
        raw = '+' + raw.lstrip('0')
    if raw and not __import__('re').match(E164, raw):
        raise ValueError('%s is not a valid E.164 number' % raw)
    if not name:
        raise ValueError('A recipient needs a name')
    return {'name': name, 'number': raw, 'role': str(entry.get('role', 'manager')).strip()[:30]}


def append_log(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')


def read_log(limit=50):
    if not LOG.exists():
        return []
    rows = []
    for line in LOG.read_text(encoding='utf-8').splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def wa_link(number, text):
    """WhatsApp's official click-to-chat link. No account, no template, no cost."""
    return 'https://wa.me/%s?text=%s' % (urllib.parse.quote(number.lstrip('+')),
                                          urllib.parse.quote(text, safe=''))


def build_summary(assistant_obj, camera_id=None, previous=None):
    """<=1000 character briefing built from the same measured values as the chat."""
    stats, events_path = assistant_obj._stats(camera_id)
    stamp = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')
    if stats is None:
        return {'generated_at': stamp, 'text': 'Store briefing %s\nNo camera is monitoring, so there is '
                                               'nothing to report.' % stamp,
                'measurement': {'state': 'no_data'}, 'facts': [], 'sources': ['live.stats()']}

    health = assistant.health_note(stats)
    zones = assistant.zone_lines(camera_id or stats.get('id'), stats)
    cues = stats.get('inspection_cues') or []
    events = assistant.read_events(events_path)
    window = float(assistant_obj.config_hint) if hasattr(assistant_obj, 'config_hint') else 3600.0

    facts = []
    top = assistant.busiest(zones)
    if top:
        live_now = top.get('occupancy') if top.get('occupancy') is not None else top.get('peak')
        facts.append('Busiest zone: %s at %s people now, peak %s.'
                     % (top['label'], assistant._fmt(live_now), assistant._fmt(top['peak'])))
    for zone in zones[:3]:
        if zone.get('dwell_tracks'):
            facts.append('Partial visible dwell: %s averages %ss across %s partial segments.'
                         % (zone['label'], assistant._fmt(zone['dwell_s']), zone['dwell_tracks']))
            break
    trend = assistant.trend_from_log(events, top['zone'] if top else None, window)
    if trend:
        facts.append('Last %ss: peak %s people, mean %s.'
                     % (assistant._fmt(trend['window_s']), assistant._fmt(trend['peak']),
                        assistant._fmt(trend['mean'], 2)))
    if cues:
        cue = cues[0]
        facts.append('Review cue: %s. %s' % (cue.get('zone_label') or cue.get('zone'), cue.get('message', '')))
    else:
        facts.append('No review cues active.')
    facts.append('Data quality: %s' % health['text'])

    action = ('Suggested check: walk %s and confirm whether the layout needs attention.'
              % top['label']) if top else 'Suggested check: start a camera to collect data.'

    header = 'Store briefing %s | %s' % (stamp, health['state'])
    text = '\n'.join([header] + facts + [action])
    if len(text) > 1000:
        text = text[:960].rsplit('\n', 1)[0] + '...'
    return {'generated_at': stamp, 'text': text, 'measurement': health,
            'facts': facts, 'zones': zones, 'cues': cues, 'sources': ['live.stats()', 'observations.jsonl']}


class BriefingService:
    def __init__(self, assistant_obj):
        self.assistant = assistant_obj
        self.config = load_config()
        self._task = None
        self._stop = threading.Event()
        self._lock = threading.RLock()   # reentrant: update() calls snapshot()

    # ---- config -----------------------------------------------------------
    def snapshot(self):
        with self._lock:
            cfg = dict(self.config)
        cfg['frequencies'] = FREQUENCIES
        cfg['deliveries'] = read_log(20)
        cfg['next_due_in_s'] = self._next_due_in()
        return cfg

    def update(self, patch):
        with self._lock:
            reschedule = any(k in patch for k in ('recipients', 'frequency_minutes', 'paused'))
            if 'recipients' in patch:
                self.config['recipients'] = [validate_recipient(r) for r in patch['recipients']]
            if 'frequency_minutes' in patch:
                minutes = int(patch['frequency_minutes'])
                if minutes not in FREQUENCIES:
                    raise ValueError('frequency must be one of %s' % FREQUENCIES)
                self.config['frequency_minutes'] = minutes
            if reschedule and self.config.get('recipients'):
                # Re-arm from now so the countdown is meaningful instead of waiting for a
                # manual send that may never happen.
                self.config['armed_at'] = time.time()
            if 'paused' in patch:
                self.config['paused'] = bool(patch['paused'])
            if 'whatsapp_mode' in patch:
                mode = patch['whatsapp_mode']
                if mode not in ('deep_link', 'clipboard'):
                    raise ValueError('whatsapp_mode must be deep_link or clipboard')
                self.config['whatsapp_mode'] = mode
            save_config(self.config)
            return self.snapshot()

    def _next_due_in(self):
        anchor = self.config.get('last_sent_at') or self.config.get('armed_at')
        if self.config.get('paused') or not anchor:
            return None
        due = anchor + self.config['frequency_minutes'] * 60
        return max(0, int(due - time.time()))

    # ---- delivery ---------------------------------------------------------
    def confirm(self, at, number):
        """Mark a prepared briefing as actually sent by a person.

        Click-to-chat has no receipt: the message is only sent when the recipient presses
        send. Recording the human's confirmation keeps the log honest about what happened.
        """
        rows = read_log(200)
        for row in reversed(rows):
            if row.get('at') == at and str(row.get('number')) == str(number):
                row['status'] = 'sent_confirmed'
                row['confirmed_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open('w', encoding='utf-8') as handle:
                    for item in rows:
                        handle.write(json.dumps(item, ensure_ascii=False) + '\n')
                return True
        return False

    def send_now(self, camera_id=None, recipients=None):
        summary = build_summary(self.assistant, camera_id)
        targets = recipients if recipients is not None else self.config.get('recipients', [])
        mode = self.config.get('whatsapp_mode', 'deep_link')
        deliveries = []
        for target in targets:
            link = wa_link(target['number'], summary['text'])
            record = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      'name': target['name'], 'number': target['number'],
                      'mode': mode,
                      'status': 'link_ready',   # prepared for a human to press send; not a delivery receipt
                      'link': link,
                      'message': summary['text']}
            append_log(record)
            deliveries.append(record)
        if targets:
            self.config['last_sent_at'] = time.time()
            save_config(self.config)
        return {'summary': summary, 'deliveries': deliveries,
                'note': ('Each recipient gets a WhatsApp link with the message pre-filled; they press send. '
                         'This uses no business account and costs nothing.')}

    # ---- scheduler --------------------------------------------------------
    def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        while not self._stop.is_set():
            try:
                cfg = self.config
                anchor = cfg.get('last_sent_at') or cfg.get('armed_at')
                due = (not cfg.get('paused') and cfg.get('recipients') and anchor
                       and time.time() >= anchor + cfg['frequency_minutes'] * 60)
                if due:
                    await asyncio.to_thread(self.send_now)
            except Exception as error:            # never let the loop kill the app
                append_log({'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                            'status': 'error', 'detail': str(error)[:200]})
            await asyncio.sleep(20)

    def stop(self):
        self._stop.set()