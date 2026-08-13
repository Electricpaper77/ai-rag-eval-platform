import json
def test_compare_route_proof_and_labels(client, tmp_path, monkeypatch):
 from backend.app.routes import recruiter_compare as r
 monkeypatch.setattr(r,'PROOF',tmp_path/'proof.json')
 page=client.get('/compare?baseline=baseline-demo&candidate=candidate-demo')
 assert page.status_code==200 and 'Deterministic Demo' in page.text
 data=client.get('/api/compare?baseline=baseline-demo&candidate=candidate-demo').json()
 assert data['baseline']['run_id']=='baseline-demo' and data['candidate']['run_id']=='candidate-demo'
 assert data['decision']['value']=='BLOCK' and data['counts']['FIXED']==1 and data['counts']['REGRESSED']==1
 proof=json.loads(client.get('/api/compare/proof').text)
 assert proof['baseline_run_id']=='baseline-demo' and proof['checksum']
 assert client.get('/api/compare?baseline=bad').status_code==404
