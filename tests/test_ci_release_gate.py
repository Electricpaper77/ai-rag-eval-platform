import json
from scripts.ci_release_gate import main
def test_ship_and_block_exit_contract(tmp_path, capsys):
    ship=tmp_path/'ship.json'; block=tmp_path/'block.json'
    assert main(['--scenario','ship','--output',str(ship)])==0
    assert main(['--scenario','block','--output',str(block)])==2
    assert json.loads(ship.read_text())['decision']=='SHIP'
    assert json.loads(block.read_text())['decision']=='BLOCK'
    assert 'api_key' not in capsys.readouterr().out.lower()
