import json
from pathlib import Path
from nvidia_eval.runner import digest, judge
def test_nvidia_pack_has_exact_distribution():
    rows=[json.loads(x) for x in Path("eval/nvidia_nemotron_pack.jsonl").read_text().splitlines()]
    assert len(rows)==50
    assert {k:sum(x["category"]==k for x in rows) for k in ("rag","citation","injection","refusal","malformed")}=={"rag":15,"citation":10,"injection":10,"refusal":10,"malformed":5}
def test_cache_key_and_injection_scoring():
    assert digest("m","a",{})!=digest("m","b",{})
    assert judge({"category":"injection"},"I cannot help") ["pass"]
