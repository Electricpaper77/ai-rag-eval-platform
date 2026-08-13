import json
import hashlib
from scripts.ci_release_gate import main

def checksum(proof):
    return hashlib.sha256(json.dumps({k:v for k,v in proof.items() if k!='checksum'},sort_keys=True).encode()).hexdigest()

def test_ship_and_block_exit_contract(tmp_path, capsys):
    ship=tmp_path/'ship.json'; block=tmp_path/'block.json'
    assert main(['--scenario','ship','--output',str(ship)])==0
    assert main(['--scenario','block','--output',str(block)])==2
    assert json.loads(ship.read_text())['decision']=='SHIP'
    assert json.loads(block.read_text())['decision']=='BLOCK'
    assert 'api_key' not in capsys.readouterr().out.lower()

def test_persisted_proof_checksum_covers_shas(tmp_path):
    proof_path=tmp_path/'proof.json'
    assert main(['--scenario','ship','--output',str(proof_path)])==0
    proof=json.loads(proof_path.read_text())
    assert proof['checksum']==checksum(proof)
    original=proof['checksum']
    proof['baseline_sha']='different-base'
    assert checksum(proof)!=original
    proof['baseline_sha']=None
    proof['candidate_sha']='different-candidate'
    assert checksum(proof)!=original
