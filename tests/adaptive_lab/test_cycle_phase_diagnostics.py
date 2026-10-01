import pytest
from app.lab_v2_shadow.cli import _cycle_phase
from .conftest import START


class Journal:
    def __init__(self):self.rows=[]
    def append(self,kind,identity,document,**kwargs):
        self.rows.append((kind,identity,document))


def test_started_phase_is_visible_before_long_work_finishes():
    journal=Journal()
    with _cycle_phase(journal,"ADAPTIVE_SHADOW",START):
        assert len(journal.rows)==1 and journal.rows[0][2]["status"]=="STARTED"
    assert journal.rows[1][2]["status"]=="COMPLETED"
    assert journal.rows[1][2]["duration_seconds"]>=0
    assert journal.rows[0][1]!=journal.rows[1][1]


def test_failure_phase_preserves_original_error_without_sensitive_text():
    journal=Journal()
    with pytest.raises(ValueError,match="synthetic-secret"):
        with _cycle_phase(journal,"PUBLICATION_PREPARATION",START):
            raise ValueError("synthetic-secret")
    assert journal.rows[-1][2]["status"]=="FAILED"
    assert "synthetic-secret" not in str(journal.rows)
