"""Model-free tests for the labeled-JD loader and metric helpers in scripts/eval_poc_accuracy.py.

Covers format validation (Issue #500), the synthetic template, and the
no-file / bad-flag paths of the CLI. Does not load the spaCy model.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "tests" / "poc" / "fixtures" / "synthetic_labeled_jd_TEMPLATE.json"


@pytest.fixture(scope="module")
def ev() -> ModuleType:
    """Import scripts/eval_poc_accuracy.py as a module (it is not a package)."""
    spec = importlib.util.spec_from_file_location("eval_poc_accuracy", ROOT / "scripts" / "eval_poc_accuracy.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "x1",
        "source_note": "SYNTHETIC: test entry",
        "text": "Write Python services.",
        "expected_skills": ["write python services"],
        "expected_technologies": ["python"],
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "labeled.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestTemplate:
    def test_template_exists_with_one_or_two_examples(self, ev: ModuleType) -> None:
        entries = ev.load_labeled_jds(TEMPLATE)
        assert 1 <= len(entries) <= 2

    def test_every_template_entry_is_marked_synthetic(self, ev: ModuleType) -> None:
        for entry in ev.load_labeled_jds(TEMPLATE):
            assert entry["source_note"].startswith("SYNTHETIC")
            assert "SYNTHETIC" in entry["text"]

    def test_template_name_flags_it_as_synthetic(self) -> None:
        assert TEMPLATE.name.startswith("synthetic_")
        assert "TEMPLATE" in TEMPLATE.name


class TestLoaderValidation:
    def test_valid_file_round_trips(self, ev: ModuleType, tmp_path: Path) -> None:
        path = _write(tmp_path, [_entry(), _entry(id="x2", expected_skills=[], expected_technologies=[])])
        entries = ev.load_labeled_jds(path)
        assert [e["id"] for e in entries] == ["x1", "x2"]

    def test_empty_list_is_valid(self, ev: ModuleType, tmp_path: Path) -> None:
        assert ev.load_labeled_jds(_write(tmp_path, [])) == []

    @pytest.mark.parametrize(
        "payload",
        [
            {"id": "x1"},  # top level not a list
            ["not an object"],
            [_entry(text="")],  # empty text
            [_entry(id="  ")],  # blank id
            [_entry(expected_skills="write python")],  # not a list
            [_entry(expected_technologies=[1])],  # non-string element
            [_entry(expected_skills=[""])],  # blank element
            [_entry(source_note=None)],  # wrong type
        ],
    )
    def test_rejects_malformed_entries(self, ev: ModuleType, tmp_path: Path, payload: object) -> None:
        with pytest.raises(ev.LabeledJDError):
            ev.load_labeled_jds(_write(tmp_path, payload))

    def test_rejects_missing_key(self, ev: ModuleType, tmp_path: Path) -> None:
        entry = _entry()
        del entry["source_note"]
        with pytest.raises(ev.LabeledJDError, match="missing keys"):
            ev.load_labeled_jds(_write(tmp_path, [entry]))

    def test_rejects_unexpected_key(self, ev: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(ev.LabeledJDError, match="unexpected keys"):
            ev.load_labeled_jds(_write(tmp_path, [_entry(expected_skils=[])]))

    def test_rejects_duplicate_ids(self, ev: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(ev.LabeledJDError, match="duplicate id"):
            ev.load_labeled_jds(_write(tmp_path, [_entry(), _entry()]))

    def test_rejects_invalid_json(self, ev: ModuleType, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("[{", encoding="utf-8")
        with pytest.raises(ev.LabeledJDError, match="invalid JSON"):
            ev.load_labeled_jds(path)


class TestCliAndHelpers:
    def test_no_flag_leaves_labeled_path_unset(self, ev: ModuleType) -> None:
        assert ev.parse_args([]).labeled_jds is None

    def test_explicit_flag_is_parsed(self, ev: ModuleType, tmp_path: Path) -> None:
        path = _write(tmp_path, [])
        assert ev.parse_args(["--labeled-jds", str(path)]).labeled_jds == path

    def test_missing_explicit_file_is_an_error(self, ev: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            ev.parse_args(["--labeled-jds", str(tmp_path / "absent.json")])
        assert exc.value.code == 2

    def test_default_path_lives_under_gitignored_data_dir(self, ev: ModuleType) -> None:
        assert ev.DEFAULT_LABELED_JDS == ROOT / "data" / "poc" / "labeled_jds.json"

    def test_rate_reports_na_on_zero_denominator(self, ev: ModuleType) -> None:
        assert ev.rate(0, 0) == "N/A"
        assert ev.rate(1, 2) == "1/2=0.50"

    def test_norm_lowercases_strips_and_dedupes(self, ev: ModuleType) -> None:
        assert ev.norm([" Python", "python ", "AWS"]) == ["aws", "python"]
