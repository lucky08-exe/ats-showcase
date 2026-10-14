"""Integration tests for full TUI workflow (Phase 5)."""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.tui.models.state import PhaseStatus, StateManager
from src.tui.panels.assess_panel import AssessPanel
from src.tui.panels.crawl_panel import CrawlPanel
from src.tui.panels.export_panel import ExportPanel
from src.tui.panels.preprocess_panel import PreprocessPanel


class TestPhaseSequence:
    """Test state transitions across full workflow phases."""

    def test_workflow_start_state(self, state_manager: StateManager) -> None:
        """Initial state has all phases idle."""
        for phase in ["crawl", "preprocess", "assess", "export"]:
            assert state_manager.phase_status[phase] == PhaseStatus.IDLE
            assert state_manager.phase_metrics[phase].processed_items == 0

    def test_crawl_phase_transitions(self, state_manager: StateManager) -> None:
        """Crawl phase transitions correctly: idle → running → complete."""
        state_manager.start_phase("crawl", total_items=10)
        assert state_manager.phase_status["crawl"] == PhaseStatus.RUNNING
        assert state_manager.phase_metrics["crawl"].total_items == 10

        for _ in range(10):
            state_manager.increment_phase_progress("crawl", tokens=100)

        state_manager.complete_phase("crawl")
        assert state_manager.phase_status["crawl"] == PhaseStatus.COMPLETED
        assert state_manager.phase_metrics["crawl"].processed_items == 10

    def test_cascading_phase_progression(self, state_manager: StateManager) -> None:
        """Phases progress in sequence: crawl → preprocess → assess → export."""
        phases = ["crawl", "preprocess", "assess", "export"]
        job_counts = [5, 5, 5, 5]

        for phase, count in zip(phases, job_counts, strict=True):
            state_manager.start_phase(phase, total_items=count)
            assert state_manager.phase_status[phase] == PhaseStatus.RUNNING

            for _ in range(count):
                state_manager.increment_phase_progress(phase, tokens=150)

            state_manager.complete_phase(phase)
            assert state_manager.phase_status[phase] == PhaseStatus.COMPLETED
            assert state_manager.phase_metrics[phase].processed_items == count

    def test_error_phase_halts_workflow(self, state_manager: StateManager) -> None:
        """Error in phase stops workflow."""
        state_manager.start_phase("assess", total_items=5)
        state_manager.increment_phase_progress("assess", tokens=100)

        error_msg = "API rate limit exceeded"
        state_manager.error_phase("assess", error_msg)

        assert state_manager.phase_status["assess"] == PhaseStatus.ERROR
        assert error_msg in state_manager.current_errors


class TestCostAccumulation:
    """Test token and cost tracking across phases."""

    def test_cumulative_tokens_across_phases(self, state_manager: StateManager) -> None:
        """Total tokens accumulate correctly."""
        assert state_manager.total_tokens_used == 0

        state_manager.start_phase("crawl", total_items=2)
        state_manager.increment_phase_progress("crawl", tokens=200)
        state_manager.increment_phase_progress("crawl", tokens=300)
        state_manager.complete_phase("crawl")

        state_manager.start_phase("preprocess", total_items=2)
        state_manager.increment_phase_progress("preprocess", tokens=150)
        state_manager.increment_phase_progress("preprocess", tokens=250)
        state_manager.complete_phase("preprocess")

        assert state_manager.total_tokens_used == 200 + 300 + 150 + 250

    def test_cumulative_cost_across_phases(self, state_manager: StateManager) -> None:
        """Total cost accumulates correctly."""
        assert state_manager.total_cost_usd == 0.0

        state_manager.start_phase("assess", total_items=1)
        state_manager.increment_phase_progress("assess", tokens=500, cost=0.0015)
        state_manager.complete_phase("assess")

        state_manager.start_phase("export", total_items=1)
        state_manager.increment_phase_progress("export", tokens=50, cost=0.00015)
        state_manager.complete_phase("export")

        expected_cost = 0.0015 + 0.00015
        assert abs(state_manager.total_cost_usd - expected_cost) < 0.000001


class TestJobDataFlow:
    """Test job data persistence and updates through workflow."""

    def test_add_and_update_job(self, state_manager: StateManager) -> None:
        """Jobs can be added and updated."""
        state_manager.add_job("job_1", "Python Dev", "TechCorp")
        assert "job_1" in state_manager.jobs
        assert state_manager.jobs["job_1"]["title"] == "Python Dev"

        state_manager.update_job("job_1", status="confirmed", score=85)
        assert state_manager.jobs["job_1"]["status"] == "confirmed"
        assert state_manager.jobs["job_1"]["score"] == 85

    def test_top_matches_sorting(self, state_manager: StateManager) -> None:
        """Top matches sorted by overall_score descending."""
        jobs = [
            {"id": "j1", "title": "Dev", "overall_score": 65},
            {"id": "j2", "title": "Lead", "overall_score": 95},
            {"id": "j3", "title": "Junior", "overall_score": 55},
            {"id": "j4", "title": "Senior", "overall_score": 90},
            {"id": "j5", "title": "Architect", "overall_score": 88},
        ]

        state_manager.update_top_matches(jobs)

        assert len(state_manager.top_matches) == 5
        assert state_manager.top_matches[0]["overall_score"] == 95  # j2
        assert state_manager.top_matches[1]["overall_score"] == 90  # j4
        assert state_manager.top_matches[4]["overall_score"] == 55  # j3

    def test_top_matches_limited_to_five(self, state_manager: StateManager) -> None:
        """Top matches never exceeds 5 items."""
        jobs = [{"id": f"j{i}", "title": f"Job {i}", "overall_score": 100 - i} for i in range(10)]

        state_manager.update_top_matches(jobs)

        assert len(state_manager.top_matches) == 5
        assert state_manager.top_matches[0]["overall_score"] == 100
        assert state_manager.top_matches[4]["overall_score"] == 96


class _FakeClock:
    """Controllable replacement for datetime.now() in src.tui.models.state."""

    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, 12, 0, 0)

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    """Patch StateManager's time source so elapsed time is deterministic."""
    clock = _FakeClock()

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            return clock.current

    monkeypatch.setattr("src.tui.models.state.datetime", _FakeDatetime)
    return clock


class TestPhaseMetricsCalculation:
    """Test ETA, throughput, and progress calculations."""

    def test_progress_percent_calculation(self, state_manager: StateManager) -> None:
        """Progress percentage calculated correctly."""
        state_manager.start_phase("crawl", total_items=100)
        assert state_manager.phase_metrics["crawl"].progress_percent == 0.0

        for _ in range(25):
            state_manager.increment_phase_progress("crawl", tokens=100)

        assert state_manager.phase_metrics["crawl"].progress_percent == 25.0

    def test_throughput_calculation(self, state_manager: StateManager, fake_clock: _FakeClock) -> None:
        """Items per second calculated from elapsed time."""
        state_manager.start_phase("assess", total_items=10)

        # Process 2 items over 0.1 fake seconds (0.05 s per item)
        for _ in range(2):
            state_manager.increment_phase_progress("assess", tokens=200)
            fake_clock.advance(0.05)

        throughput = state_manager.phase_metrics["assess"].items_per_second
        assert throughput == pytest.approx(2 / 0.1)  # 20 items/sec

    def test_eta_seconds_calculation(self, state_manager: StateManager, fake_clock: _FakeClock) -> None:
        """ETA estimated from throughput and remaining items."""
        state_manager.start_phase("export", total_items=10)

        # Process 2 items over 0.1 fake seconds to establish throughput
        for _ in range(2):
            state_manager.increment_phase_progress("export", tokens=100)
            fake_clock.advance(0.05)

        eta = state_manager.phase_metrics["export"].eta_seconds
        remaining = 10 - 2

        # 8 remaining items at 20 items/sec
        assert eta == pytest.approx(remaining / (2 / 0.1))  # 0.4 s


class TestErrorHandling:
    """Test error collection and reporting."""

    def test_errors_accumulate(self, state_manager: StateManager) -> None:
        """Errors accumulate in current_errors list."""
        assert len(state_manager.current_errors) == 0

        state_manager.start_phase("crawl", total_items=1)
        state_manager.increment_phase_progress("crawl", tokens=0, error="Selector failed")

        assert len(state_manager.current_errors) == 1
        assert "Selector failed" in state_manager.current_errors

    def test_failed_item_count(self, state_manager: StateManager) -> None:
        """Failed items tracked separately."""
        state_manager.start_phase("crawl", total_items=5)

        for i in range(5):
            if i % 2 == 0:
                state_manager.increment_phase_progress("crawl", tokens=100)
            else:
                state_manager.increment_phase_progress("crawl", tokens=0, error=f"Error {i}")

        metrics = state_manager.phase_metrics["crawl"]
        assert metrics.processed_items == 5
        assert metrics.failed_items == 2  # i=1,3 failed (even indices succeed)


class TestPausedState:
    """Test pause/resume workflow control."""

    def test_pause_resume_toggle(self, state_manager: StateManager) -> None:
        """Paused state toggles correctly."""
        assert state_manager.paused is False

        state_manager.paused = True
        assert state_manager.paused is True

        state_manager.paused = False
        assert state_manager.paused is False

    def test_paused_state_in_workflow(self, state_manager: StateManager) -> None:
        """Paused state persists during workflow."""
        state_manager.start_phase("crawl", total_items=5)
        state_manager.paused = True

        assert state_manager.paused is True
        assert state_manager.phase_status["crawl"] == PhaseStatus.RUNNING


class TestLargeDataset:
    """Test performance with large job datasets."""

    def test_thousand_jobs_state_management(self, state_manager: StateManager) -> None:
        """StateManager handles 1000+ jobs efficiently."""
        state_manager.start_phase("assess", total_items=1000)

        # Add 1000 jobs
        for i in range(1000):
            state_manager.add_job(
                f"job_{i}",
                f"Job Title {i}",
                f"Company {i % 50}",
                overall_score=i % 100,
            )

        assert len(state_manager.jobs) == 1000

        # Update top matches with all jobs
        jobs_list = list(state_manager.jobs.values())
        state_manager.update_top_matches(jobs_list)

        # Top 5 should be highest scores
        assert len(state_manager.top_matches) == 5
        scores = [j["overall_score"] for j in state_manager.top_matches]
        assert scores == sorted(scores, reverse=True)

    def test_thousand_phases_processed(self, state_manager: StateManager) -> None:
        """Metrics accumulate correctly over 1000+ items."""
        state_manager.start_phase("assess", total_items=1000)

        for _ in range(1000):
            state_manager.increment_phase_progress("assess", tokens=100, cost=0.0003)

        metrics = state_manager.phase_metrics["assess"]
        assert metrics.processed_items == 1000
        assert metrics.total_tokens == 100000
        assert abs(metrics.total_cost_usd - 0.3) < 0.001
