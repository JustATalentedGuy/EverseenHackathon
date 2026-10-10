"""Optional local-LLM phrase pass (llama.cpp or Ollama).

Both runtimes execute the same GGUF weights; only the runner differs. llama.cpp
ships a single static `llama-server` binary exposing an OpenAI-compatible
endpoint, which avoids Ollama's bundled runtime (~1-2 GB on disk) and its
background daemon. Ollama remains supported for convenience (`ollama pull`).

`qwen3:1.7b` scored highest on a CPU-only tool-calling benchmark (0.960 agent
score, perfect restraint) and a quantization study found no significant
degradation at Q4_K_M. It is still only used to rephrase an answer that was
already composed from measured values, so a missing or slow model degrades the
assistant to its deterministic path instead of breaking it.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = os.environ.get('ASSISTANT_BACKEND', 'auto').strip().lower()   # auto|llamacpp|ollama|none
MODEL = os.environ.get('ASSISTANT_MODEL', 'qwen3:1.7b')
GGUF = os.environ.get('ASSISTANT_GGUF', '')            # path to the .gguf for llama.cpp
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434')
LLAMACPP_URL = os.environ.get('LLAMACPP_URL', 'http://127.0.0.1:8081')
TIMEOUT_S = float(os.environ.get('ASSISTANT_LLM_TIMEOUT', '12'))

SPOKEN_CONTRACT = (
    'Output format for spoken answers, in this exact order: '
    '(1) ANSWER FIRST - the direct answer is the opening clause, never postponed behind context. '
    '(2) ONE HEADLINE NUMBER - at most one figure that matters; a second only if it changes the decision. '
    '(3) CONTEXT ONLY IF IT CHANGES THE DECISION - one short clause, or omit it. '
    '(4) TRUST FIRST - if the measurement is not reliable, say so in the opening sentence, not as a footnote. '
    '(5) A HOOK - end with one short offer to go deeper, such as "Want the per-zone breakdown?" '
    'Two to three spoken sentences in total. '
    'Never read a table, a list of every zone, or a metric definition aloud unless asked for one specifically. '
    'Speak numbers the way a person says them: "90th percentile" becomes "nine times out of ten", '
    '"5.3 seconds" becomes "about five seconds", and a percentage becomes "about a third of the time". '
    'Never say "observed", "partial visible dwell" or "camera-local" in speech; those belong on screen, not aloud.'
)

SYSTEM = (
    'You are the store-operations voice assistant for the Everseen Dwell-Time & Bottleneck Mapper. '
    'You rewrite an already-correct, evidence-backed answer into something a manager wants to LISTEN to '
    'on a shop floor: brief, direct, conversational, and useful. ' + SPOKEN_CONTRACT + ' '
    'Truth rules, which outrank the format above: never invent, round, convert or calculate any number; '
    'copy every figure exactly as given; never add a claim that is not in the supplied answer; '
    'never mention unique shoppers, store-wide totals, checkout waits, revenue or anyone\'s identity. '
    'Plain text only: no markdown, no bullets, no emoji, no URLs, no code.'
)


def _get(url, timeout=1.5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status == 200


def _post(url, body, timeout):
    request = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


class Phraser:
    """Thin adapter over whichever local runtime is available. Never raises."""

    def __init__(self, backend=BACKEND, model=MODEL, gguf=GGUF):
        self.backend = backend
        self.model = model
        self.gguf = gguf
        self._ready = None

    # ---- detection --------------------------------------------------------
    def _detect(self):
        if self.backend == 'none':
            return 'none'
        if self.backend in ('auto', 'llamacpp') and self.gguf and Path(self.gguf).is_file() \
                and _get(LLAMACPP_URL + '/health'):
            return 'llamacpp'
        if self.backend in ('auto', 'ollama'):
            try:
                if _get(OLLAMA_URL + '/api/tags'):
                    names = {m.get('name', '') for m in json.loads(
                        urllib.request.urlopen(OLLAMA_URL + '/api/tags', timeout=1.5).read().decode('utf-8')
                    ).get('models', [])}
                    if any(n == self.model or n.split(':')[0] == self.model.split(':')[0] for n in names):
                        return 'ollama'
            except Exception:
                pass
        return 'none'

    def ready(self):
        if self._ready is None:
            self._ready = self._detect()
        return self._ready != 'none'

    # ---- generation -------------------------------------------------------
    def _complete(self, facts):
        # Branch on the *detected* backend: with ASSISTANT_BACKEND=auto the requested
        # backend stays 'auto' while _ready holds what was actually found.
        if self._ready == 'llamacpp':
            body = {'model': 'local', 'temperature': 0.2, 'max_tokens': 160,
                    'chat_template_kwargs': {'enable_thinking': False},
                    'messages': [{'role': 'system', 'content': SYSTEM},
                                 {'role': 'user', 'content': facts + ' /no_think'}]}
            data = _post(LLAMACPP_URL + '/v1/chat/completions', body, TIMEOUT_S)
            return (data.get('choices', [{}])[0].get('message', {}).get('content') or '').strip()
        body = {'model': self.model, 'stream': False, 'think': False,
                'options': {'temperature': 0.2, 'num_predict': 160},
                'messages': [{'role': 'system', 'content': SYSTEM},
                             {'role': 'user', 'content': facts}]}
        data = _post(OLLAMA_URL + '/api/chat', body, TIMEOUT_S)
        return (data.get('message', {}).get('content') or '').strip()

    def phrase(self, question, answer, payload):
        if not self.ready():
            return None
        facts = json.dumps({
            'answer_to_rewrite': answer,
            'measurement_state': payload.get('measurement', {}).get('state'),
            'zones': [{k: z.get(k) for k in ('label', 'occupancy', 'peak', 'p90', 'dwell_s', 'entries')}
                      for z in payload.get('zones', [])][:6],
            'active_cues': len(payload.get('cues') or []),
        }, ensure_ascii=False)
        try:
            text = self._complete(facts)
            return text if 0 < len(text) <= 600 else None
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None


def build():
    phraser = Phraser()
    return phraser if phraser.ready() else None