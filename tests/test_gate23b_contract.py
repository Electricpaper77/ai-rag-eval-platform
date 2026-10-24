import csv
import io

from saas.router import _csv_value, _detail_payload


def test_csv_export_escapes_formula_cells():
    for value in ("=1+1", "+SUM(A1)", "-danger", "@cmd"):
        assert _csv_value(value).startswith("'")
    output = io.StringIO()
    csv.writer(output).writerow([_csv_value("=1+1")])
    assert output.getvalue().startswith("'=1+1")


def test_detail_payload_reports_missing_evidence_without_inventing_metrics():
    payload = _detail_payload({"id": "run_1", "status": "completed", "result_json": None, "evidence_metadata_json": "{}"})
    assert payload["result"] is None
    assert payload["evidence"] == {}
    assert payload["missing_evidence"] == ["result", "evidence"]


def test_detail_payload_preserves_recorded_result_and_evidence():
    payload = _detail_payload({"result_json": '{"score": 0.8}', "evidence_metadata_json": '{"citations": 2}'})
    assert payload["result"] == {"score": 0.8}
    assert payload["evidence"] == {"citations": 2}
    assert payload["missing_evidence"] == []

