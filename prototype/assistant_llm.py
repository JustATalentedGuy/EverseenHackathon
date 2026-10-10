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

BACKEND = os.environ.get('ASSISTANT_BACKEND', 'auto').strip().lower()  # auto|llamacpp|ollama|cloud|none
MODEL = os.environ.get('ASSISTANT_MODEL', 'qwen3:1.7b')
GGUF = os.environ.get('ASSISTANT_GGUF', '')            # path to the .gguf for llama.cpp
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434')
LLAMACPP_URL = os.environ.get('LLAMACPP_URL', 'http://127.0.0.1:8081')
TIMEOUT_S = float(os.environ.get('ASSISTANT_LLM_TIMEOUT', '12'))

# Optional cloud fallback. Any OpenAI-compatible endpoint works (Groq, OpenRouter, ...).
# The key is read from the environment and never stored or logged: only the composed answer
# and its measured figures are sent, never video, images or the raw observation log.
CLOUD_URL = os.environ.get('ASSISTANT_CLOUD_URL', 'https://api.groq.com/openai/v1').rstrip('/')
CLOUD_MODEL = os.environ.get('ASSISTANT_CLOUD_MODEL', 'qwen/qwen3.8-27b')
CLOUD_KEY = os.environ.get('ASSISTANT_CLOUD_API_KEY') or os.environ.get('GROQ_API_KEY') or ''

SPOKEN_CONTRACT = (
    'Output format for spoken answers, in this exact order: '
    '(1) ANSWER FIRST - the direct answer is the opening clause, never postponed behind context. '
    '(2) ONE HEADLINE NUMBER - at most one figure that matters; a second only if it changes the decision. '
    '(3) CONTEXT ONLY IF IT CHANGES THE DECISION - one short clause, or omit it. '
    '(4) TRUST FIRST - if the measurement is not reliable, say so in the opening sentence, not as a footnote. '
    '(5) THE NEXT STEP - when something is flagged, say the single place a person should walk to. '
    '(6) A HOOK - end with one short offer, such as "Want me to keep watching that?" '
    'Two to three spoken sentences in total. '
    'Sound like a colleague on the shop floor, not a report: use contractions, name things plainly, '
    'and address the listener as "you". Never open with the metric name itself - say what is happening, '
    'not what the field is called. '
    'Never read a table, a list of every zone, or a metric definition aloud unless asked for one specifically. '
    'Speak numbers the way a person says them: "90th percentile" becomes "nine times out of ten", '
    '"5.3 seconds" becomes "about five seconds", and a percentage becomes "about a third of the time". '
    'Never say "observed", "partial visible dwell", "camera-local", "percentile" or "threshold" in speech; '
    'say "I can see", "time they spend", "the cameras", and "your limit" instead.'
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


# The shared prompt is written for live answers and would turn a definition into a status
# claim ("the data is stale") when handed explanatory text. This one may only restate.
DOCUMENT_SYSTEM = (
    'You explain a documented metric or rule to a shopkeeper, in your own warm, spoken words. '
    'Rules: keep the meaning exactly as given, in the same order, and do not shorten it into a '
    'different claim. Never say anything about the shop right now - no cameras, no occupancy, no '
    '"currently", "at the moment", or "I cannot see". You are explaining what the words mean, '
    'not reporting a status. Do not add numbers that are not in the text, and do not drop any '
    'that are. Two or three spoken sentences. Use contractions and plain names, never the internal '
    'terms "partial visible dwell", "camera-local", "P90" or "threshold" - say "the time you can '
    'actually see someone", "the cameras", "nine times out of ten" and "your limit". '
    'End with one short offer, such as "Want me to show that for your floor right now?" '
    'Plain text only: no markdown, no bullets, no source names.'
)


def _get(url, timeout=1.5):
    request = urllib.request.Request(url, headers={'User-Agent': 'everseen-prototype/1.0'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status == 200


def _post(url, body, timeout, headers=None):
    # Groq sits behind Cloudflare, which rejects Python's default urllib User-Agent
    # with error 1010 ("browser signature banned"), so send an ordinary one.
    request = urllib.request.Request(
        url, data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                 'User-Agent': 'everseen-prototype/1.0 (+local analytics)', **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


_WORD_NUMBERS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
                 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
                 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
                 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20}


def _figures_preserved(source, text):
    """Every figure in the source answer must survive the rewrite.

    Models paraphrase. Left unchecked they will quietly drop "peak 7" or turn a count
    into a different one, which turns a phrasing pass into a data error. Digits are
    accepted in either form, because the contract asks for "five" over "5".
    """
    import re
    digits = re.findall(r'\d+', text)
    words = {w for w in re.findall(r'[a-z]+', text.lower()) if w in _WORD_NUMBERS}
    values = {int(d) for d in digits} | {_WORD_NUMBERS[w] for w in words}
    values |= {int(d) for d in digits}          # compound forms like "twenty-two"
    for compound in re.findall(r'([a-z]+)-([a-z]+)', text.lower()):
        tens, ones = _WORD_NUMBERS.get(compound[0]), _WORD_NUMBERS.get(compound[1])
        if tens is not None and ones is not None:
            values.add(tens + ones)
    for number in re.findall(r'\d+', source):
        if int(number) not in values:
            return False
    return True


class Phraser:
    """Thin adapter over whichever local runtime is available. Never raises."""

    def __init__(self, backend=BACKEND, model=MODEL, gguf=GGUF):
        self.backend = backend
        self.model = model
        self.gguf = gguf
        self._ready = None
        self.cloud = bool(CLOUD_KEY)

    # ---- detection --------------------------------------------------------
    def _detect(self):
        if self.backend == 'none':
            return 'none'
        if self.backend == 'cloud':
            return 'cloud' if CLOUD_KEY else 'none'
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
        # auto: a configured cloud key is the last resort, after the local runtimes
        if self.backend == 'auto' and CLOUD_KEY:
            return 'cloud'
        return 'none'

    def ready(self):
        if self._ready is None:
            self._ready = self._detect()
        return self._ready != 'none'

    # ---- generation -------------------------------------------------------
    @staticmethod
    def _cloud(facts, system=None):
        body = {'model': CLOUD_MODEL, 'temperature': 0.3, 'max_tokens': 512,
                'messages': [{'role': 'system', 'content': system or SYSTEM},
                             {'role': 'user', 'content': facts}]}
        data = _post(CLOUD_URL + '/chat/completions', body, TIMEOUT_S,
                     headers={'Authorization': 'Bearer ' + CLOUD_KEY})
        message = data.get('choices', [{}])[0].get('message', {})
        return (message.get('content') or '').strip()

    def _complete(self, facts, system=None):
        system = system or SYSTEM
        if self._ready == 'cloud':
            return self._cloud(facts, system)
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
                'messages': [{'role': 'system', 'content': system or SYSTEM},
                             {'role': 'user', 'content': facts}]}
        data = _post(OLLAMA_URL + '/api/chat', body, TIMEOUT_S)
        return (data.get('message', {}).get('content') or '').strip()

    def phrase(self, question, answer, payload, system=None):
        """Rewrite an answer. `system` defaults to the live-answer contract."""
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
            text = self._complete(facts, system)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None
        if not text or len(text) > 600:
            return None
        # A rewrite that loses a figure is worse than no rewrite: keep the measured answer.
        if not _figures_preserved(answer, text):
            return None
        for term in ('unique shopper', 'unique visitor', 'revenue', 'checkout wait'):
            if term in text.lower():
                return None                     # the model broke a refusal boundary
        return text


def build():
    phraser = Phraser()
    return phraser if phraser.ready() else None


def describe(phraser):
    """Human-readable backend for the dashboard, without ever exposing the key."""
    if phraser is None:
        return 'none (template answers)'
    active = phraser._ready or 'unknown'
    label = {'llamacpp': 'llama.cpp', 'ollama': 'Ollama', 'cloud': 'cloud (%s)' % CLOUD_MODEL}.get(active, active)
    return '%s · %s' % (label, phraser.model if active != 'cloud' else CLOUD_MODEL)