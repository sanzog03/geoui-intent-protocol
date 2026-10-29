"""The utility's turn rows are a superset of the demo notebook's manual log rows."""

from geouibench.records import ErrorRecord, TurnRecord, TurnUsage
from worldview.agents.benchmark import log as notebook_log


def test_turn_record_is_a_superset_of_the_notebook_row():
    ours = set(TurnRecord.model_fields)
    theirs = set(notebook_log.TurnRecord.model_fields)
    assert theirs <= ours, theirs - ours
    assert set(notebook_log.TurnUsage.model_fields) <= set(TurnUsage.model_fields)
    assert set(notebook_log.ErrorRecord.model_fields) <= set(ErrorRecord.model_fields)


def test_a_notebook_row_validates_as_ours():
    row = notebook_log.TurnRecord(
        agent="geoui", session_id="abc", turn_index=1, user_prompt="hi", wall_clock_s=1.0, output_kind="text"
    )
    ours = TurnRecord.model_validate_json(row.model_dump_json())
    assert ours.source == "simulated" and ours.golden_name is None
