"""Observer output compatibility and exact recovery, with no real transport."""
from copy import deepcopy
import pytest
from app.admin_alerts.output_contracts import expected_document
from app.admin_alerts.model import UNITS
from test_quality_compatibility import observer

@pytest.mark.parametrize("live,scope", [
    ("NOT_EVALUATED", None), ("NOT_EVALUATED", "LIVE_OBSERVER"),
    ("ENABLED", "PREMATCH_OBSERVER"), ("UNKNOWN", "PREMATCH_OBSERVER"),
    ("NOT_EVALUATED", []),
])
def test_unknown_or_unscoped_live_is_not_completion_proof(live, scope):
    doc = observer()
    doc.update(LIVE=live, LIVE_SCOPE=scope)
    assert not expected_document(UNITS[2], doc)

@pytest.mark.parametrize("change", [
    {"heavy_training":True}, {"api_calls":1}, {"telegram_sends":1},
    {"stream":"LIVE"}, {"created_at":"invalid"}, {"linkage":None},
    {"state":[]}, {"metrics":None},
])
def test_new_scope_preserves_existing_final_output_guards(change):
    doc = observer()
    doc.update(LIVE="NOT_EVALUATED", LIVE_SCOPE="PREMATCH_OBSERVER")
    assert expected_document(UNITS[2], doc)
    assert not expected_document(UNITS[2], {**doc, **change})

def test_both_formats_leave_evidence_immutable():
    for extra in ({}, {"LIVE":"NOT_EVALUATED", "LIVE_SCOPE":"PREMATCH_OBSERVER"}):
        doc = {**observer(), **extra}
        before = deepcopy(doc)
        assert expected_document(UNITS[2], doc)
        assert doc == before
