"""Tests for StateManager and related models."""

from datetime import datetime, timedelta
from typing import Any

import pytest

from src.tui.models.state import PhaseMetrics, PhaseStatus, StateManager


class _FakeClock:
    """Controllable replacement for datetime.now() in src.tui.models.state."""

    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, 12, 0, 0)

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    """Patch PhaseMetrics' time source so elapsed time is deterministic."""
    clock = _FakeClock()

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            return clock.current

    monkeypatch.setattr("src.tui.models.state.datetime", _FakeDatetime)
    return clock


class TestPhaseMetrics:
    """Tests for PhaseMetrics dataclass."""

    def test_initialization(self):
        """Test PhaseMetrics initializes with defaults."""
        metrics = PhaseMetrics()
        assert metrics.total_items == 0
        assert metrics.processed_items == 0
        assert metrics.failed_items == 0
        assert metrics.total_tokens == 0
        assert metrics.total_cost_usd == 0.0
        assert metrics.start_time is None
        assert metrics.end_time is None

    def test_progress_percent_empty(self):
        """Progress is 0% when no items."""
        metrics = PhaseMetrics(total_items=0, processed_items=0)
        assert metrics.progress_percent == 0.0

    def test_progress_percent_half(self):
        """Progress calculated correctly at 50%."""
        metrics = PhaseMetrics(total_items=100, processed_items=50)
        assert metrics.progress_percent == 50.0

    def test_progress_percent_complete(self):
        """Progress is 100% when all items processed."""
        metrics = PhaseMetrics(total_items=100, processed_items=100)
        assert metrics.progress_percent == 100.0

    def test_progress_percent_fractional(self):
        """Progress handles fractional results."""
        metrics = PhaseMetrics(total_items=3, processed_items=1)
        assert abs(metrics.progress_percent - 33.333333) < 0.01

    def test_elapsed_seconds_no_start(self):
        """Elapsed is 0 when phase not started."""
        metrics = PhaseMetrics(start_time=None)
        assert metrics.elapsed_seconds == 0.0

    def test_elapsed_seconds_running(self, fake_clock):
        """Elapsed time calculated while phase running."""
        start = fake_clock.current
        fake_clock.advance(5)
        metrics = PhaseMetrics(start_time=start, end_time=None)
        assert metrics.elapsed_seconds == pytest.approx(5.0)

    def test_elapsed_seconds_completed(self):
        """Elapsed time uses end_time when phase complete."""
        start = datetime(2026, 1, 1, 12, 0, 0)
        end = start + timedelta(seconds=5)
        metrics = PhaseMetrics(start_time=start, end_time=end)
        assert metrics.elapsed_seconds == pytest.approx(5.0)

    def test_items_per_second_no_elapsed(self):
        """Speed is 0 when elapsed time is 0."""
        metrics = PhaseMetrics(start_time=None, processed_items=10)
        assert metrics.items_per_second == 0.0

    def test_items_per_second_calculated(self, fake_clock):
        """Speed calculated correctly."""
        start = fake_clock.current
        fake_clock.advance(2)
        metrics = PhaseMetrics(start_time=start, processed_items=10)
        assert metrics.items_per_second == pytest.approx(5.0)  # 10 items / 2s

    def test_eta_seconds_no_speed(self):
        """ETA is 0 when speed is 0."""
        metrics = PhaseMetrics(
            total_items=100,
            processed_items=0,
            start_time=None,
        )
        assert metrics.eta_seconds == 0.0

    def test_eta_seconds_calculated(self, fake_clock):
        """ETA calculated correctly."""
        start = fake_clock.current
        fake_clock.advance(10)
        metrics = PhaseMetrics(
            start_time=start,
            total_items=100,
            processed_items=10,
        )
        # Processed 10 in 10s = 1 item/sec, 90 remaining = 90s ETA
        assert metrics.eta_seconds == pytest.approx(90.0)

    def test_eta_seconds_almost_done(self, fake_clock):
        """ETA is small when nearly complete."""
        start = fake_clock.current
        fake_clock.advance(10)
        metrics = PhaseMetrics(
            start_time=start,
            total_items=100,
            processed_items=99,
        )
        # Processed 99 in 10s = 9.9 items/sec, 1 remaining = ~0.101s ETA
        assert metrics.eta_seconds == pytest.approx(1 / 9.9)


class TestPhaseStatus:
    """Tests for PhaseStatus enum."""

    def test_phase_status_values(self):
        """All phase statuses are defined."""
        assert PhaseStatus.IDLE.value == "idle"
        assert PhaseStatus.RUNNING.value == "running"
        assert PhaseStatus.PAUSED.value == "paused"
        assert PhaseStatus.COMPLETED.value == "completed"
        assert PhaseStatus.ERROR.value == "error"


class TestStateManager:
    """Tests for StateManager class."""

    def test_initialization(self, state_manager):
        """StateManager initializes with all phases idle."""
        assert state_manager.phase_status["crawl"] == PhaseStatus.IDLE
        assert state_manager.phase_status["preprocess"] == PhaseStatus.IDLE
        assert state_manager.phase_status["assess"] == PhaseStatus.IDLE
        assert state_manager.phase_status["export"] == PhaseStatus.IDLE
        assert len(state_manager.jobs) == 0
        assert len(state_manager.top_matches) == 0
        assert len(state_manager.current_errors) == 0
        assert state_manager.paused is False

    def test_start_phase(self, state_manager):
        """start_phase initializes phase with running status."""
        state_manager.start_phase("crawl", total_items=42)

        assert state_manager.phase_status["crawl"] == PhaseStatus.RUNNING
        assert state_manager.phase_metrics["crawl"].total_items == 42
        assert state_manager.phase_metrics["crawl"].processed_items == 0
        assert state_manager.phase_metrics["crawl"].start_time is not None

    def test_increment_phase_progress(self, state_manager):
        """increment_phase_progress tracks items, tokens, cost."""
        state_manager.start_phase("crawl", total_items=10)
        state_manager.increment_phase_progress("crawl", tokens=150, cost=0.0005)

        metrics = state_manager.phase_metrics["crawl"]
        assert metrics.processed_items == 1
        assert metrics.total_tokens == 150
        assert metrics.total_cost_usd == 0.0005

    def test_increment_phase_progress_multiple(self, state_manager):
        """increment_phase_progress accumulates across multiple calls."""
        state_manager.start_phase("crawl", total_items=10)

        for _ in range(3):
            state_manager.increment_phase_progress("crawl", tokens=100, cost=0.0003)

        metrics = state_manager.phase_metrics["crawl"]
        assert metrics.processed_items == 3
        assert metrics.total_tokens == 300
        assert metrics.total_cost_usd == 0.0009

    def test_increment_phase_progress_with_error(self, state_manager):
        """increment_phase_progress tracks errors."""
        state_manager.start_phase("crawl", total_items=10)
        state_manager.increment_phase_progress("crawl", error="Network timeout")

        metrics = state_manager.phase_metrics["crawl"]
        assert metrics.failed_items == 1
        assert "Network timeout" in state_manager.current_errors

    def test_complete_phase(self, state_manager):
        """complete_phase marks phase complete."""
        state_manager.start_phase("crawl", total_items=10)
        state_manager.complete_phase("crawl")

        assert state_manager.phase_status["crawl"] == PhaseStatus.COMPLETED
        assert state_manager.phase_metrics["crawl"].end_time is not None

    def test_error_phase(self, state_manager):
        """error_phase marks phase failed."""
        state_manager.start_phase("crawl", total_items=10)
        state_manager.error_phase("crawl", "Database connection failed")

        assert state_manager.phase_status["crawl"] == PhaseStatus.ERROR
        assert state_manager.phase_metrics["crawl"].end_time is not None
        assert "Database connection failed" in state_manager.current_errors

    def test_add_job(self, state_manager):
        """add_job registers a job."""
        state_manager.add_job("job1", "Senior Python Dev", "TechCorp")

        assert "job1" in state_manager.jobs
        assert state_manager.jobs["job1"]["title"] == "Senior Python Dev"
        assert state_manager.jobs["job1"]["company"] == "TechCorp"
        assert state_manager.jobs["job1"]["status"] == "pending_review"

    def test_add_job_with_kwargs(self, state_manager):
        """add_job supports additional attributes."""
        state_manager.add_job(
            "job1",
            "Backend Engineer",
            "StartupXYZ",
            location="Remote",
            salary_min=100000,
        )

        job = state_manager.jobs["job1"]
        assert job["location"] == "Remote"
        assert job["salary_min"] == 100000

    def test_update_job(self, state_manager):
        """update_job modifies job data."""
        state_manager.add_job("job1", "Title", "Company")
        state_manager.update_job("job1", status="confirmed", score=85)

        assert state_manager.jobs["job1"]["status"] == "confirmed"
        assert state_manager.jobs["job1"]["score"] == 85

    def test_update_job_nonexistent(self, state_manager):
        """update_job silently ignores nonexistent job."""
        state_manager.update_job("nonexistent", status="confirmed")
        # Should not raise, just do nothing

    def test_update_top_matches_empty(self, state_manager):
        """update_top_matches handles empty list."""
        state_manager.update_top_matches([])
        assert state_manager.top_matches == []

    def test_update_top_matches_sorting(self, state_manager):
        """update_top_matches sorts by overall_score descending."""
        matches = [
            {"id": "1", "overall_score": 50},
            {"id": "2", "overall_score": 100},
            {"id": "3", "overall_score": 75},
        ]
        state_manager.update_top_matches(matches)

        # Should be sorted: 100, 75, 50
        assert state_manager.top_matches[0]["overall_score"] == 100
        assert state_manager.top_matches[1]["overall_score"] == 75
        assert state_manager.top_matches[2]["overall_score"] == 50

    def test_update_top_matches_truncates_to_five(self, state_manager):
        """update_top_matches keeps only top 5."""
        matches = [{"id": str(i), "overall_score": 100 - i} for i in range(10)]
        state_manager.update_top_matches(matches)

        assert len(state_manager.top_matches) == 5
        # Top 5 should have scores 100, 99, 98, 97, 96
        for i, match in enumerate(state_manager.top_matches):
            assert match["overall_score"] == 100 - i

    def test_total_tokens_used(self, state_manager):
        """total_tokens_used aggregates across phases."""
        state_manager.start_phase("crawl", total_items=2)
        state_manager.increment_phase_progress("crawl", tokens=100)
        state_manager.increment_phase_progress("crawl", tokens=50)

        state_manager.start_phase("preprocess", total_items=2)
        state_manager.increment_phase_progress("preprocess", tokens=200)

        assert state_manager.total_tokens_used == 350

    def test_total_cost_usd(self, state_manager):
        """total_cost_usd aggregates across phases."""
        state_manager.start_phase("crawl", total_items=2)
        state_manager.increment_phase_progress("crawl", cost=0.0005)
        state_manager.increment_phase_progress("crawl", cost=0.0003)

        state_manager.start_phase("preprocess", total_items=1)
        state_manager.increment_phase_progress("preprocess", cost=0.0002)

        total = state_manager.total_cost_usd
        assert abs(total - 0.001) < 1e-10

    def test_workflow_scenario(self, state_manager):
        """Full workflow: crawl → preprocess → assess → export."""
        # Crawl phase
        state_manager.start_phase("crawl", total_items=3)
        for i in range(3):
            state_manager.add_job(f"job{i}", f"Title {i}", f"Company {i}")
            state_manager.increment_phase_progress("crawl", tokens=100)
        state_manager.complete_phase("crawl")

        # Preprocess phase
        state_manager.start_phase("preprocess", total_items=3)
        for _ in range(3):
            state_manager.increment_phase_progress("preprocess", tokens=200)
        state_manager.complete_phase("preprocess")

        # Assess phase with top matches
        state_manager.start_phase("assess", total_items=3)
        matches = [
            {"id": "job0", "overall_score": 95},
            {"id": "job1", "overall_score": 87},
            {"id": "job2", "overall_score": 72},
        ]
        state_manager.update_top_matches(matches)
        for _ in range(3):
            state_manager.increment_phase_progress("assess", tokens=300, cost=0.0009)
        state_manager.complete_phase("assess")

        # Verify final state
        assert state_manager.phase_status["crawl"] == PhaseStatus.COMPLETED
        assert state_manager.phase_status["preprocess"] == PhaseStatus.COMPLETED
        assert state_manager.phase_status["assess"] == PhaseStatus.COMPLETED
        assert state_manager.total_tokens_used == 300 + 600 + 900
        assert abs(state_manager.total_cost_usd - 0.0027) < 1e-10
        assert len(state_manager.top_matches) == 3
        assert state_manager.top_matches[0]["overall_score"] == 95
