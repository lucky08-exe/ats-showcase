"""Tests for batch_processor config hardening (Issue #624).

Tests validate:
1. --company flag with non-dict company value exits with code 1, no traceback
2. --company flag with missing config dir exits with code 1, no traceback
3. _resolve_description_selector with non-string description_selector raises ValueError
4. load_all_company_configs loads UTF-8 BOM files without error
5. resolve_company_selectors skips non-string name entries and succeeds on valid lookups
6. source_config with surrounding whitespace resolves correctly
7. resolve_company_selectors strips whitespace from job_company_name
"""

import json

import pytest

from src.poc.tweak.common import load_all_company_configs, resolve_company_selectors


class TestConfigHardeningMainPath:
    """Tests for --company path error handling in main() (Issue #624 Item 1, 2)."""

    def test_company_flag_with_non_dict_company_value_exits_1_no_traceback(self, tmp_path, capsys):
        """Test --company with non-dict company value (e.g., "x" string) exits 1 without traceback.

        Config: {"companies": {"AlphaCo": "x"}} (malformed, non-dict value).
        Expected: main() returns 1, stderr has "Error:", no "Traceback".
        """
        # SYNTHETIC: malformed config with string company value instead of dict
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(json.dumps({"companies": {"AlphaCo": "x"}}))

        # Create a test input file
        input_file = tmp_path / "jobs.json"
        input_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",  # SYNTHETIC: generic placeholder
                        "company": "TechCorp",  # SYNTHETIC: placeholder
                        "description": "<p>placeholder</p>",  # SYNTHETIC: minimal HTML
                    }
                ]
            )
        )

        # Act
        import sys

        from src.poc.tweak.batch_processor import main

        old_argv = sys.argv
        try:
            sys.argv = [
                "batch_processor",
                "--input-path",
                str(input_file),
                "--company",
                "AlphaCo",
                "--config-dir",
                str(config_dir),
            ]
            exit_code = main()

            # Assert
            assert exit_code == 1, "main() should return 1 on malformed config"
            captured = capsys.readouterr()
            assert "Error:" in captured.err, "stderr should have 'Error:' prefix"
            assert "Traceback" not in captured.err, "stderr should not have traceback"
        finally:
            sys.argv = old_argv

    def test_company_flag_with_missing_config_dir_exits_1_no_traceback(self, tmp_path, capsys):
        """Test --company with nonexistent config dir exits 1 without traceback.

        Expected: main() returns 1, stderr has "Error:", no "Traceback".
        """
        # Create a test input file
        input_file = tmp_path / "jobs.json"
        input_file.write_text(
            json.dumps(
                [
                    {
                        "id": "job1",
                        "title": "Developer",  # SYNTHETIC: placeholder
                        "company": "TechCorp",  # SYNTHETIC: placeholder
                        "description": "<p>placeholder</p>",  # SYNTHETIC: minimal
                    }
                ]
            )
        )

        # Act
        import sys

        from src.poc.tweak.batch_processor import main

        old_argv = sys.argv
        try:
            sys.argv = [
                "batch_processor",
                "--input-path",
                str(input_file),
                "--company",
                "AlphaCo",
                "--config-dir",
                str(tmp_path / "nonexistent"),
            ]
            exit_code = main()

            # Assert
            assert exit_code == 1, "main() should return 1 on missing config dir"
            captured = capsys.readouterr()
            assert "Error:" in captured.err, "stderr should have 'Error:' prefix"
            assert "Traceback" not in captured.err, "stderr should not have traceback"
        finally:
            sys.argv = old_argv


class TestResolveDescriptionSelectorHardening:
    """Tests for _resolve_description_selector non-string check (Issue #624 Item 3)."""

    def test_resolve_description_selector_non_string_raises_valueerror(self, tmp_path):
        """Test _resolve_description_selector with non-string description_selector (list) raises ValueError.

        Config: {"companies": {"AlphaCo": {"name": "...", "selectors": {"description_selector": ["a", "b"]}}}}
        Expected: ValueError mentioning "non-string".
        """
        # SYNTHETIC: config with list instead of string for description_selector
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(
            json.dumps(
                {
                    "companies": {
                        "AlphaCo": {
                            "name": "Alpha Co",
                            "selectors": {
                                # SYNTHETIC: list instead of CSS selector string
                                "description_selector": ["a", "b"],
                                "title": "h1",
                            },
                        }
                    }
                }
            )
        )

        # Act & Assert
        from src.poc.tweak.batch_processor import _resolve_description_selector

        with pytest.raises(ValueError) as exc_info:
            _resolve_description_selector("AlphaCo", str(config_dir))

        assert "non-string" in str(exc_info.value)
        assert "description_selector" in str(exc_info.value)


class TestLoadAllCompanyConfigsBOM:
    """Tests for load_all_company_configs UTF-8 BOM support (Issue #624 Item 4)."""

    def test_load_all_company_configs_bom_file_loads_without_warning(self, tmp_path):
        """Test load_all_company_configs loads UTF-8 BOM file successfully.

        Expected: returns companies dict without raising, BOM is transparently handled.
        """
        # SYNTHETIC: JSON config with UTF-8 BOM prefix
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "bom_test.json"

        # Write with UTF-8 BOM prefix
        bom_json = json.dumps(
            {
                "companies": {
                    "AlphaCo": {
                        "name": "Alpha Co",
                        "selectors": {"description_selector": ".desc"},
                    }
                }
            }
        )
        with open(config_file, "wb") as f:
            # UTF-8 BOM: U+FEFF
            f.write(b"\xef\xbb\xbf" + bom_json.encode("utf-8"))

        # Act
        companies = load_all_company_configs(str(config_dir))

        # Assert
        assert "AlphaCo" in companies, "BOM file should load companies successfully"
        assert companies["AlphaCo"]["name"] == "Alpha Co"


class TestResolveCompanySelectorsSafety:
    """Tests for resolve_company_selectors robustness (Issue #624 Item 5, 7)."""

    def test_resolve_company_selectors_skips_non_string_name(self):
        """Test resolve_company_selectors skips non-string name and succeeds on valid lookup.

        Config has a company with "name": 5 (non-string), plus valid "AlphaCo".
        Expected: lookup by "Alpha Co" returns AlphaCo's selectors, no crash.
        """
        # SYNTHETIC: merged config with non-string name entry
        merged_config = {
            "Zeta": {
                "name": 5,  # SYNTHETIC: int instead of string
                "selectors": {"description_selector": ".zeta"},
            },
            "AlphaCo": {
                "name": "Alpha Co",
                "selectors": {"description_selector": ".alpha"},
            },
        }

        # Act
        selectors = resolve_company_selectors("Alpha Co", merged_config)

        # Assert
        assert selectors["description_selector"] == ".alpha"

    def test_resolve_company_selectors_strips_whitespace_from_input(self):
        """Test resolve_company_selectors strips whitespace from job_company_name.

        Input: job_company_name=" AlphaCo " (surrounding whitespace).
        Expected: matches key "AlphaCo" after stripping.
        """
        # SYNTHETIC: config with whitespace-sensitive lookup
        merged_config = {
            "AlphaCo": {
                "name": "Alpha Co",
                "selectors": {"description_selector": ".alpha"},
            }
        }

        # Act
        selectors = resolve_company_selectors(" AlphaCo ", merged_config)

        # Assert
        assert selectors["description_selector"] == ".alpha"

    def test_resolve_company_selectors_with_non_dict_company_value_returns_empty(self):
        """Test resolve_company_selectors with non-dict company value returns empty dict.

        Config: {"AlphaCo": "x"} (string value, not dict).
        Expected: resolve_company_selectors("AlphaCo", config) returns {} without raise.
        """
        # SYNTHETIC: config with non-dict company value (string instead of selector dict)
        merged_config = {"AlphaCo": "x"}

        # Act
        selectors = resolve_company_selectors("AlphaCo", merged_config)

        # Assert - should safely return empty dict, no AttributeError
        assert selectors == {}


class TestSourceConfigWhitespaceScoping:
    """Tests for source_config whitespace stripping (Issue #624 Item 6)."""

    def test_source_config_whitespace_is_stripped_in_run_batch(self, tmp_path, monkeypatch):
        """Test that source_config with surrounding whitespace resolves correctly.

        Job has source_config=" AlphaCo " (with spaces).
        Expected: matches config key "AlphaCo" after stripping, selector applied.
        """
        # SYNTHETIC: job record with whitespace in source_config
        from src.poc.tweak import batch_processor as bp

        # Track calls to _resolve_job_scoping to verify stripping
        calls = []
        original_resolver = bp._resolve_job_scoping

        def tracking_resolver(source_config, config_dir):
            calls.append(source_config)
            return original_resolver(source_config, config_dir)

        monkeypatch.setattr(bp, "_resolve_job_scoping", tracking_resolver)

        # Create config with AlphaCo
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "test.json"
        config_file.write_text(
            json.dumps(
                {
                    "companies": {
                        "AlphaCo": {
                            "name": "Alpha Co",
                            "selectors": {"description_selector": ".alpha"},
                        }
                    }
                }
            )
        )

        # Create jobs with whitespace-padded source_config
        input_file = tmp_path / "jobs.json"
        input_file.write_text(
            json.dumps(
                [
                    {
                        "id": "alpha-ws",
                        "title": "Developer",  # SYNTHETIC: placeholder
                        "company": "X",  # SYNTHETIC: placeholder
                        "description": "<p>placeholder</p>",  # SYNTHETIC: minimal
                        "source_config": " AlphaCo ",  # SYNTHETIC: whitespace-padded
                    }
                ]
            )
        )

        # Act
        results = bp.run_batch(str(input_file), config_dir=str(config_dir))

        # Assert - resolver should have been called with "AlphaCo" after stripping
        assert len(calls) > 0, "resolver should be called for source_config"
        assert "AlphaCo" in calls, f"resolver should be called with stripped key, got {calls}"
        assert len(results) == 1
        assert not results[0].has_errors(), f"job should process without error: {results[0].errors}"
