"""Model-free tests for corpus mode in scripts/eval_poc_accuracy.py (Issue #552).

Covers sentence splitting, corpus discovery, deterministic dumps, the compare
diff, CLI validation and an end-to-end run with stub extractors. Does not load
the spaCy model: spacy.load and the extractor classes are replaced in the
script module by monkeypatch.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def ev() -> ModuleType:
    """Import scripts/eval_poc_accuracy.py as a module (it is not a package)."""
    spec = importlib.util.spec_from_file_location("eval_poc_accuracy", ROOT / "scripts" / "eval_poc_accuracy.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _skill_fn(text: str) -> list[str]:
    return ["Deploy Models"] if "deploy" in text.lower() else []


def _tech_fn(text: str) -> list[str]:
    return [w for w in ("python", "aws") if w in text.lower()]


class TestSplitSentences:
    def test_breaks_after_terminal_punctuation(self, ev: ModuleType) -> None:
        assert ev.split_sentences("Write Python. Ship AWS! Done?") == ["Write Python.", "Ship AWS!", "Done?"]

    def test_strips_markdown_markers_and_drops_dividers(self, ev: ModuleType) -> None:
        text = "# Requirements\n- Python services.\n1. Deploy models.\n> Quoted line.\n---\n\n"
        assert ev.split_sentences(text) == ["Requirements", "Python services.", "Deploy models.", "Quoted line."]

    def test_each_line_is_its_own_block(self, ev: ModuleType) -> None:
        assert ev.split_sentences("first line\nsecond line") == ["first line", "second line"]

    def test_empty_and_whitespace_input(self, ev: ModuleType) -> None:
        assert ev.split_sentences("") == []
        assert ev.split_sentences("   \n\t\n") == []


class TestCollectCorpus:
    def _tree(self, root: Path) -> Path:
        (root / "sub").mkdir(parents=True)
        (root / "b.md").write_text("Beta sentence.", encoding="utf-8")
        (root / "a.json").write_text('{"k": "Alpha sentence."}', encoding="utf-8")
        (root / "sub" / "c.md").write_text("Gamma sentence.", encoding="utf-8")
        (root / "ignored.txt").write_text("Not read.", encoding="utf-8")
        return root

    def test_directory_is_searched_recursively_for_md_and_json(self, ev: ModuleType, tmp_path: Path) -> None:
        corpus = self._tree(tmp_path / "corpus")
        prefixes = [prefix for prefix, _ in ev.collect_corpus(str(corpus))]
        assert prefixes == ["a.json", "b.md", "sub/c.md"]

    def test_glob_uses_literal_prefix_for_ids(self, ev: ModuleType, tmp_path: Path) -> None:
        corpus = self._tree(tmp_path / "corpus")
        pattern = str(corpus / "**" / "*.md")
        prefixes = [prefix for prefix, _ in ev.collect_corpus(pattern)]
        assert prefixes == ["b.md", "sub/c.md"]

    def test_single_file_is_accepted(self, ev: ModuleType, tmp_path: Path) -> None:
        corpus = self._tree(tmp_path / "corpus")
        assert [p for p, _ in ev.collect_corpus(str(corpus / "b.md"))] == ["b.md"]

    def test_missing_path_is_a_clear_error(self, ev: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(ev.CorpusError, match="corpus path not found"):
            ev.collect_corpus(str(tmp_path / "nope"))

    def test_empty_directory_is_a_clear_error(self, ev: ModuleType, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        with pytest.raises(ev.CorpusError, match="no .md or .json files"):
            ev.collect_corpus(str(tmp_path / "empty"))

    def test_glob_with_no_matches_is_a_clear_error(self, ev: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(ev.CorpusError, match="no .md or .json files"):
            ev.collect_corpus(str(tmp_path / "*.md"))


class TestBuildRecords:
    def test_json_uses_string_values_only_in_order(self, ev: ModuleType, tmp_path: Path) -> None:
        path = tmp_path / "d.json"
        path.write_text(json.dumps({"x": "One. Two.", "y": ["Three."], "n": 4}), encoding="utf-8")
        records = ev.build_records([("d.json", path)])
        assert records == [
            ("d.json:00000", "One."),
            ("d.json:00001", "Two."),
            ("d.json:00002", "Three."),
        ]

    def test_invalid_json_is_a_clear_error(self, ev: ModuleType, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ev.CorpusError, match="invalid JSON"):
            ev.build_records([("bad.json", path)])

    def test_corpus_without_sentences_is_a_clear_error(self, ev: ModuleType, tmp_path: Path) -> None:
        path = tmp_path / "blank.md"
        path.write_text("\n---\n\n", encoding="utf-8")
        with pytest.raises(ev.CorpusError, match="no sentences"):
            ev.build_records([("blank.md", path)])


class TestDumpAndCompare:
    def _dump(self, ev: ModuleType, records: list[tuple[str, str]]) -> dict[str, Any]:
        dump: dict[str, Any] = ev.build_dump(records, _skill_fn, _tech_fn)
        return dump

    def test_dump_is_normalised_and_sorted(self, ev: ModuleType) -> None:
        dump = self._dump(ev, [("b.md:00000", "Deploy AWS."), ("a.md:00000", "Plain.")])
        assert list(dump["sentences"]) == ["a.md:00000", "b.md:00000"]
        assert dump["sentences"]["b.md:00000"] == {"text": "Deploy AWS.", "skills": ["deploy models"], "tech": ["aws"]}

    def test_written_dump_bytes_are_deterministic(self, ev: ModuleType, tmp_path: Path) -> None:
        records = [("a.md:00000", "Python and AWS."), ("a.md:00001", "Deploy models.")]
        first, second = tmp_path / "one.json", tmp_path / "two.json"
        ev.write_dump(first, self._dump(ev, records))
        ev.write_dump(second, self._dump(ev, list(reversed(records))))
        assert first.read_bytes() == second.read_bytes()

    def test_load_round_trips_written_dump(self, ev: ModuleType, tmp_path: Path) -> None:
        dump = self._dump(ev, [("a.md:00000", "Python.")])
        path = tmp_path / "d.json"
        ev.write_dump(path, dump)
        assert ev.load_dump(path) == dump

    def test_load_rejects_foreign_json(self, ev: ModuleType, tmp_path: Path) -> None:
        path = tmp_path / "other.json"
        path.write_text(json.dumps({"sentences": {}}), encoding="utf-8")
        with pytest.raises(ev.CorpusError, match="not a eval_poc_corpus_dump"):
            ev.load_dump(path)

    def test_load_rejects_malformed_sentence(self, ev: ModuleType, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        data = {"schema": ev.DUMP_SCHEMA, "version": ev.DUMP_VERSION, "sentences": {"x": {"text": "t"}}}
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ev.CorpusError, match="must have text, skills and tech"):
            ev.load_dump(path)

    def test_identical_dumps_have_no_changes(self, ev: ModuleType) -> None:
        dump = self._dump(ev, [("a.md:00000", "Python.")])
        result = ev.compare_dumps(dump, dump)
        assert result["changed"] == [] and result["added"] == [] and result["removed"] == []
        assert result["common"] == 1

    def test_skill_and_tech_changes_are_reported_with_before_and_after(self, ev: ModuleType) -> None:
        before = self._dump(ev, [("a.md:00000", "Deploy on AWS.")])
        after = json.loads(json.dumps(before))
        after["sentences"]["a.md:00000"]["skills"] = []
        after["sentences"]["a.md:00000"]["tech"] = ["python"]
        result = ev.compare_dumps(before, after)
        assert [sid for sid, _, _ in result["changed"]] == ["a.md:00000"]
        lines = "\n".join(ev.format_compare(result, "before.json"))
        assert "CHANGED a.md:00000" in lines
        assert "SKILLS before=['deploy models']" in lines
        assert "TECH   before=['aws']" in lines
        assert "after =['python']" in lines
        assert "SUMMARY compared=1 changed=1 added=0 removed=0" in lines

    def test_added_and_removed_sentences_are_counted(self, ev: ModuleType) -> None:
        before = self._dump(ev, [("a.md:00000", "Python."), ("a.md:00001", "AWS.")])
        after = self._dump(ev, [("a.md:00000", "Python."), ("a.md:00002", "Deploy.")])
        result = ev.compare_dumps(before, after)
        assert [sid for sid, _ in result["added"]] == ["a.md:00002"]
        assert [sid for sid, _ in result["removed"]] == ["a.md:00001"]
        assert result["changed"] == []


class TestParseArgs:
    def test_dump_without_corpus_is_rejected(self, ev: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            ev.parse_args(["--dump", str(tmp_path / "d.json")])
        assert exc.value.code == 2

    def test_missing_corpus_path_is_rejected(self, ev: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            ev.parse_args(["--corpus", str(tmp_path / "missing")])
        assert exc.value.code == 2

    def test_missing_compare_file_is_rejected(self, ev: ModuleType, tmp_path: Path) -> None:
        (tmp_path / "c").mkdir()
        with pytest.raises(SystemExit) as exc:
            ev.parse_args(["--corpus", str(tmp_path / "c"), "--compare", str(tmp_path / "nope.json")])
        assert exc.value.code == 2

    def test_corpus_cannot_combine_with_labeled_jds(self, ev: ModuleType, tmp_path: Path) -> None:
        template = ROOT / "tests" / "poc" / "fixtures" / "synthetic_labeled_jd_TEMPLATE.json"
        with pytest.raises(SystemExit) as exc:
            ev.parse_args(["--corpus", str(tmp_path), "--labeled-jds", str(template)])
        assert exc.value.code == 2

    def test_default_invocation_has_no_corpus(self, ev: ModuleType) -> None:
        args = ev.parse_args([])
        assert args.corpus is None and args.dump is None and args.compare is None


class _StubNLP:
    meta = {"version": "stub"}

    def __call__(self, text: str) -> str:
        return text


class _StubTech:
    def __init__(self, nlp: Any) -> None:
        self.nlp = nlp

    def extract(self, doc: str) -> list[str]:
        return _tech_fn(doc)


class _StubSkill:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def extract(self, text: str) -> list[str]:
        return _skill_fn(text)


@pytest.fixture
def stubbed(ev: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(ev.spacy, "load", lambda name: _StubNLP())
    monkeypatch.setattr(ev, "SkillExtractor", _StubSkill)
    monkeypatch.setattr(ev, "TechExtractor", _StubTech)
    return ev


class TestMainCorpusMode:
    def _corpus(self, tmp_path: Path) -> Path:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "jd.md").write_text("Deploy models on AWS. Know Python.\n", encoding="utf-8")
        return corpus

    def test_dump_then_compare_reports_no_changes(
        self, stubbed: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        corpus = self._corpus(tmp_path)
        dump = tmp_path / "before.json"
        stubbed.main(["--corpus", str(corpus), "--dump", str(dump)])
        capsys.readouterr()
        stubbed.main(["--corpus", str(corpus), "--compare", str(dump)])
        out = capsys.readouterr().out
        assert "CORPUS files=1 sentences=2" in out
        assert "SUMMARY compared=2 changed=0 added=0 removed=0" in out
        assert "CHANGED" not in out

    def test_compare_prints_only_changed_sentence(
        self, stubbed: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        corpus = self._corpus(tmp_path)
        dump_path = tmp_path / "before.json"
        stubbed.main(["--corpus", str(corpus), "--dump", str(dump_path)])
        data = json.loads(dump_path.read_text(encoding="utf-8"))
        data["sentences"]["jd.md:00001"]["tech"] = []
        dump_path.write_text(json.dumps(data), encoding="utf-8")
        capsys.readouterr()
        stubbed.main(["--corpus", str(corpus), "--compare", str(dump_path)])
        out = capsys.readouterr().out
        assert "CHANGED jd.md:00001" in out
        assert "CHANGED jd.md:00000" not in out
        assert "TECH   before=[]" in out
        assert "SUMMARY compared=2 changed=1 added=0 removed=0" in out

    def test_listing_without_dump_or_compare(
        self, stubbed: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stubbed.main(["--corpus", str(self._corpus(tmp_path))])
        out = capsys.readouterr().out
        assert "jd.md:00000\tskills=['deploy models']\ttech=['aws']" in out

    def test_corpus_error_exits_one_with_message(
        self, stubbed: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(SystemExit) as exc:
            stubbed.main(["--corpus", str(empty)])
        assert exc.value.code == 1
        assert "error: no .md or .json files" in capsys.readouterr().err
