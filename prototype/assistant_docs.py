"""Small dependency-free BM25 index over the project documents.

The corpus is a handful of markdown files, so lexical retrieval is both faster
and more predictable than embeddings, and it adds nothing to requirements.txt.
Every hit carries its file and section so answers can cite them.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

DOC_FILES = [
    'research/EVERSEEN_FINAL_PROJECT_DOCUMENTATION.md',
    'research/METRICS_AND_BOTTLENECK_SIGNALS.md',
    'research/FINAL_DEADLINE_DATA_AND_DEPLOYMENT_ARCHITECTURE.md',
    'prototype/INTEGRATION.md',
    'prototype/README.md',
    'README.md',
]
STOPWORDS = set("""a an and are as at be been by can do does for from has have how i if in is it its
may of on or so than that the their there these this to was were what when where which who will with
you your not no if then also more most other such only same each any both few""".split())


def _sections(text, source):
    """Split markdown into (heading, body) chunks small enough to quote."""
    out, heading, buf = [], source, []
    for line in text.splitlines():
        if line.startswith('#'):
            if buf and heading.strip():
                out.append((heading, '\n'.join(buf).strip()))
            heading, buf = line.lstrip('#').strip(), []
        else:
            buf.append(line)
    if buf and heading.strip():
        out.append((heading, '\n'.join(buf).strip()))
    return [(h, b) for h, b in out if len(b.split()) > 12]


class DocIndex:
    def __init__(self, chunks):
        self.chunks = chunks
        self.df = Counter()
        for _, text, _title in chunks:
            for term in set(_tokens(text)):
                self.df[term] += 1
        self.n = max(1, len(chunks))
        self.avg_len = sum(len(_tokens(t)) for _, t, _x in chunks) / self.n or 1.0

    # Shopkeepers say "cue" and "dead zone"; the research notes say "review recommendation"
    # and "low occupancy". Expand the question so retrieval lands on the same passage.
    VOCABULARY = {
        'cue': 'review recommendation', 'alert': 'review recommendation',
        'flag': 'review recommendation', 'warning': 'review recommendation',
        'bottleneck': 'congestion severity persistence',
        'jam': 'congestion', 'crowding': 'crowd pressure congestion',
        'dead': 'unused low occupancy', 'empty': 'low occupancy',
        'deserted': 'low occupancy section', 'idle': 'low occupancy',
        'busy': 'occupancy throughput', 'queue': 'queueing service rate',
        'sticky': 'dwell persistence', 'linger': 'dwell',
        'people': 'person trajectory track section', 'shopper': 'person track',
    }

    def with_live(self, sections):
        """A copy of this index plus the current system state, searchable alongside the docs.

        The live chunks answer "what is happening now"; the static corpus answers "what
        does that mean". One search can now return both, which is what makes the assistant
        able to explain a bottleneck using the rule and the current numbers together.
        """
        if not sections:
            return self
        extra = []
        for source, text in sections:
            for heading, body in _sections(text, source):
                extra.append(('[%s] %s' % (source, heading), body, False))
        if not extra:
            return self
        return DocIndex(list(self.chunks) + extra)

    def search(self, query, top=3, prefer=None, only=None, exclude=None):
        terms = _tokens(query)
        for word, expansion in self.VOCABULARY.items():
            if word in query.lower().split():
                terms += _tokens(expansion)
        if not terms:
            return []
        scored = []
        for heading, text, is_title in self.chunks:
            if only and not any(name in heading for name in only):
                continue
            if exclude and any(name in heading for name in exclude):
                continue
            # "how does this system behave" should answer from the operational docs, not
            # the research notes: the research explains why, INTEGRATION says what we do.
            boost = 1.0
            if prefer and any(name in heading for name in prefer) and not is_title:
                boost = 1.35
            tokens = _tokens(text)
            if not tokens:
                continue
            tf = Counter(tokens)
            score = 0.0
            for term in terms:
                if term not in tf:
                    continue
                idf = math.log(1 + (self.n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                score += idf * tf[term] * 2.2 / (tf[term] + 1.2 * (0.25 + 0.75 * len(tokens) / self.avg_len))
            if heading and not is_title:
                score += 4.0 * sum(1 for t in terms if t in _tokens(heading))
            score *= boost
            # definitional phrasing beats a passing mention in a summary section
            if re.search(r'\b(is|are)\b[^.]{0,60}\b(defined as|means|is the)\b|=\s*sum of|\bmeans\b', text, re.I):
                score += 2.5
            if score > 0:
                scored.append((score, heading, text))
        scored.sort(reverse=True, key=lambda r: r[0])
        hits = []
        for score, heading, text in scored[:top]:
            hits.append({'heading': heading, 'text': _quote(text, terms), 'score': round(score, 2),
                         'source': _source_of(heading)})
        return hits


SOURCES = {}


def _source_of(heading):
    if heading.startswith('['):
        return heading[1:heading.index(']')]
    return SOURCES.get(heading, 'project documentation')


def _tokens(text):
    return [t for t in re.findall(r'[a-z0-9_]+', text.lower()) if t not in STOPWORDS and len(t) > 1]


def _quote(text, terms, words=70):
    body = re.sub(r'\s+', ' ', text).strip()
    lowered = body.lower()
    # prefer the longest consecutive run of query terms ("partial visible dwell")
    position, best = -1, 0
    for size in range(min(len(terms), 4), 0, -1):
        for start in range(len(terms) - size + 1):
            phrase = ' '.join(terms[start:start + size])
            found = lowered.find(phrase)
            if found != -1:
                position, best = found, size
                break
        if best:
            break
    if position == -1:
        for term in terms:
            position = lowered.find(term)
            if position != -1:
                break
    if position == -1:
        return body[:words * 8].rsplit(' ', 1)[0] + '...'
    start = max(0, body.rfind(' ', 0, max(0, position - 200)))
    end = min(len(body), position + 420)
    snippet = body[start:end].strip()
    return ('...' if start else '') + snippet + ('...' if end < len(body) else '')


KNOWLEDGE_DIR = 'runs/assistant/knowledge'


def is_ingested(source):
    return KNOWLEDGE_DIR in source


def build_index(root: Path, include_knowledge: bool = True):
    """Index the project documents plus the ingested analytics corpus.

    The knowledge folder is written by assistant_ingest from what the detector produced,
    so the assistant answers from stored analytics rather than from the video feed.
    """
    chunks = []
    sources = list(DOC_FILES)
    if include_knowledge:
        knowledge = Path(root) / KNOWLEDGE_DIR
        if knowledge.is_dir():
            sources += sorted(str(p.relative_to(Path(root)))
                              for p in knowledge.glob('*.md'))
    for rel in sources:
        path = Path(root) / rel
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        for position, (heading, body) in enumerate(_sections(text, rel)):
            SOURCES[heading] = rel
            # the document title is an index entry, not an explanation: never boost it
            chunks.append(('[%s] %s' % (rel, heading), body, position == 0))
    return DocIndex(chunks)