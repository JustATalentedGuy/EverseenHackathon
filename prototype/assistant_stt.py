"""Speech to text for the assistant, using the optional cloud key.

Kept separate from assistant_llm: transcription sends audio off the machine, so it is a
deliberate opt-in rather than a silent side effect of the phrasing backend. Without a
key the browser's own SpeechRecognition is still used and this module reports unavailable.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

URL = os.environ.get('ASSISTANT_STT_URL', 'https://api.groq.com/openai/v1').rstrip('/')
KEY = os.environ.get('ASSISTANT_CLOUD_API_KEY') or os.environ.get('GROQ_API_KEY') or ''
MODEL = os.environ.get('ASSISTANT_STT_MODEL', 'whisper-large-v3-turbo')
TIMEOUT_S = float(os.environ.get('ASSISTANT_STT_TIMEOUT', '30'))
MAX_BYTES = 25 * 1024 * 1024          # Whisper refuses anything larger


def available():
    return bool(KEY)


def transcribe(audio: bytes, filename='clip.webm'):
    """Return (text, error). `error` is a short human-readable reason on failure."""
    if not available():
        return '', 'No speech-to-text key configured'
    if not audio:
        return '', 'No audio received'
    if len(audio) > MAX_BYTES:
        return '', 'Recording is too large; keep clips under a minute'
    boundary = '----everseen' + os.urandom(12).hex()
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
             f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
             + audio + b'\r\n',
             f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{MODEL}\r\n'.encode(),
             f'--{boundary}--\r\n'.encode()]
    request = urllib.request.Request(
        URL + '/audio/transcriptions', data=b''.join(parts),
        headers={'Authorization': 'Bearer ' + KEY,
                 'Content-Type': 'multipart/form-data; boundary=' + boundary,
                 'User-Agent': 'everseen-prototype/1.0 (+local analytics)'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        return '', 'Transcription failed (%s)' % exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return '', 'Could not reach the transcription service'
    text = (data.get('text') or '').strip()
    return (text, '') if text else ('', 'Nothing recognised in that clip')