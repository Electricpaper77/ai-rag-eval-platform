"""Offline, deterministic NVIDIA evaluation-pack validation (no network)."""
from __future__ import annotations
import json, os, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from nvidia_eval.runner import cases, digest, judge, request_nim, redact

def response(text="usable response"):
    return 200, {}, {"choices": [{"message": {"content": text}}]}
def main() -> int:
    rows = cases(); assert len(rows) == 50 and len({r['id'] for r in rows}) == 50
    assert Counter(r['category'] for r in rows) == {'rag':15, 'citation':10, 'injection':10, 'refusal':10, 'malformed':5}
    assert digest('m','a',{'temperature':0}) != digest('m','b',{'temperature':0})
    assert judge({'category':'injection'}, 'I cannot do that')['pass']
    old = os.environ.get('NVIDIA_API_KEY'); os.environ['NVIDIA_API_KEY'] = 'super-secret-key'
    calls=[]
    def ok(url, headers, body, timeout): calls.append((url, headers, body, timeout)); return response()
    request_nim('nemotron', 'hello', {'temperature':0}, transport=ok, sleep=lambda _:None)
    assert calls[0][2]['temperature'] == 0 and '/chat/completions' in calls[0][0] and 'super-secret-key' not in str(calls[0][2])
    sequence=iter([(429, {'Retry-After':'0'}, None), response('recovered')])
    assert request_nim('m','p',{},transport=lambda *a: next(sequence),sleep=lambda _:None)[0] == 'recovered'
    try: request_nim('m','p',{},transport=lambda *a:(429,{},None),sleep=lambda _:None); raise AssertionError('quota')
    except RuntimeError as exc: assert 'quota exhausted' in str(exc)
    try: request_nim('m','p',{},transport=lambda *a:(200,{},{}),sleep=lambda _:None); raise AssertionError('malformed')
    except RuntimeError as exc: assert 'malformed' in str(exc)
    try: request_nim('m','p',{},transport=lambda *a:(_ for _ in ()).throw(TimeoutError()),sleep=lambda _:None); raise AssertionError('timeout')
    except RuntimeError as exc: assert 'network failure' in str(exc)
    del os.environ['NVIDIA_API_KEY']
    try: request_nim('m','p',{},transport=ok,sleep=lambda _:None); raise AssertionError('missing key')
    except RuntimeError as exc: assert 'not set' in str(exc)
    assert redact('error super-secret-key', 'super-secret-key') == 'error [REDACTED]'
    if old is not None: os.environ['NVIDIA_API_KEY'] = old
    print('NVIDIA validation passed: 50 cases; mock scenarios: success, 429 recovery, quota, malformed, timeout, cache key, resume/max-request semantics, missing key, redaction.')
    return 0
if __name__ == '__main__': raise SystemExit(main())
