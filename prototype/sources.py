"""Validate camera sources consistently for live and offline workflows.

Webcam indices, project-local files, and explicit HTTP(S)/RTSP URLs are supported.
This local-only demo does not provide an unrestricted arbitrary filesystem reader.
"""
from pathlib import Path
from urllib.parse import urlsplit


def resolve_source(source: str, root: Path):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Camera source is required')
    source = source.strip()
    if source.isascii() and source.isdecimal():
        number = int(source)
        if number > 9:
            raise ValueError('Webcam indices must be between 0 and 9')
        return number, True
    if '://' in source:
        parsed = urlsplit(source)
        if parsed.scheme.lower() not in {'http', 'https', 'rtsp'} or not parsed.hostname:
            raise ValueError('Use an HTTP(S) video URL or RTSP camera URL')
        return source, True
    path = (Path(root) / source).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError('Local videos must be existing files inside the Everseen project')
    return str(path), False
