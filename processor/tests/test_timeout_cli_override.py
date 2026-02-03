"""
Test suite for CLI timeout override feature.

Verifies that --timeout CLI argument properly overrides TimeoutConfig defaults
and scales priority-based timeouts correctly.
"""

import pytest
from pathlib import Path
from processor.config import ProcessorConfig, TimeoutConfig


class TestTimeoutCliOverride:
    """Test that CLI --timeout argument properly configures timeouts."""

    def test_default_timeout_without_cli_override(self, tmp_path: Path):
        """When no CLI timeout is provided, should use hardcoded defaults."""
        config = ProcessorConfig(
            repo_root=tmp_path,
            timeout_ms=300000,  # Default value
        )

        # TimeoutConfig should use hardcoded defaults
        assert config.timeouts.base_timeout_ms is None
        assert config.timeouts.get_timeout_for_priority("P0 Critical") == 900000  # 15 min
        assert config.timeouts.get_timeout_for_priority("P1 High") == 720000      # 12 min
        assert config.timeouts.get_timeout_for_priority("P1 Medium") == 600000    # 10 min
        assert config.timeouts.get_timeout_for_priority("P2 Low") == 600000       # 10 min
        assert config.timeouts.get_timeout_for_priority("Unknown") == 600000      # default

    def test_cli_timeout_override_sets_base(self, tmp_path: Path):
        """When CLI timeout is provided, should set base_timeout_ms."""
        config = ProcessorConfig(
            repo_root=tmp_path,
            timeout_ms=60000,  # 1 minute via CLI
        )

        # base_timeout_ms should be set from CLI
        assert config.timeouts.base_timeout_ms == 60000

    def test_priority_scaling_with_cli_override(self, tmp_path: Path):
        """Priority timeouts should scale from CLI base value."""
        config = ProcessorConfig(
            repo_root=tmp_path,
            timeout_ms=60000,  # 1 minute base
        )

        # All priorities should scale from 60000ms base
        # P0 Critical: 60000 * 1.5 = 90000 (1.5 min)
        assert config.timeouts.get_timeout_for_priority("P0 Critical") == 90000
        assert config.timeouts.get_timeout_for_priority("p0") == 90000
        assert config.timeouts.get_timeout_for_priority("critical") == 90000

        # P1 High: 60000 * 1.2 = 72000 (1.2 min)
        assert config.timeouts.get_timeout_for_priority("P1 High") == 72000
        assert config.timeouts.get_timeout_for_priority("high") == 72000

        # P1 Medium: 60000 * 1.0 = 60000 (1 min)
        assert config.timeouts.get_timeout_for_priority("P1 Medium") == 60000
        assert config.timeouts.get_timeout_for_priority("P1") == 60000
        assert config.timeouts.get_timeout_for_priority("medium") == 60000

        # P2 Low: 60000 * 1.0 = 60000 (1 min)
        assert config.timeouts.get_timeout_for_priority("P2 Low") == 60000
        assert config.timeouts.get_timeout_for_priority("P2") == 60000
        assert config.timeouts.get_timeout_for_priority("low") == 60000

        # Unknown/Default: 60000 * 1.0 = 60000
        assert config.timeouts.get_timeout_for_priority("Unknown") == 60000
        assert config.timeouts.get_timeout_for_priority("") == 60000

    def test_retry_multiplier_with_cli_override(self, tmp_path: Path):
        """Retry multiplier should apply on top of CLI-scaled base."""
        config = ProcessorConfig(
            repo_root=tmp_path,
            timeout_ms=60000,  # 1 minute base
        )

        # Attempt 1 (base)
        assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=1) == 60000

        # Attempt 2 (1.2x multiplier)
        # 60000 * 1.2 = 72000
        assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=2) == 72000

        # Attempt 3 (1.44x multiplier = 1.2^2)
        # 60000 * 1.44 = 86400
        assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=3) == 86400

        # P0 Critical with retry
        # Base: 60000 * 1.5 = 90000
        # Attempt 2: 90000 * 1.2 = 108000
        assert config.timeouts.get_timeout_for_priority("P0 Critical", attempt=2) == 108000

    def test_retry_multiplier_with_defaults(self, tmp_path: Path):
        """Retry multiplier should work with hardcoded defaults too."""
        config = ProcessorConfig(
            repo_root=tmp_path,
            timeout_ms=300000,  # Default (no CLI override)
        )

        # P1 Medium default is 600000ms
        assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=1) == 600000

        # Attempt 2: 600000 * 1.2 = 720000
        assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=2) == 720000

        # Attempt 3: 600000 * 1.44 = 864000
        assert config.timeouts.get_timeout_for_priority("P1 Medium", attempt=3) == 864000

    def test_different_cli_timeout_values(self, tmp_path: Path):
        """Test various CLI timeout values to ensure scaling works correctly."""
        # Very short timeout (30 seconds)
        config_short = ProcessorConfig(repo_root=tmp_path, timeout_ms=30000)
        assert config_short.timeouts.get_timeout_for_priority("P0 Critical") == 45000  # 30s * 1.5
        assert config_short.timeouts.get_timeout_for_priority("P1 Medium") == 30000    # 30s * 1.0

        # Medium timeout (5 minutes)
        config_medium = ProcessorConfig(repo_root=tmp_path, timeout_ms=300000)
        # This should use hardcoded defaults since 300000 is the default value
        assert config_medium.timeouts.base_timeout_ms is None

        # Long timeout (30 minutes)
        config_long = ProcessorConfig(repo_root=tmp_path, timeout_ms=1800000)
        assert config_long.timeouts.base_timeout_ms == 1800000
        assert config_long.timeouts.get_timeout_for_priority("P0 Critical") == 2700000  # 30m * 1.5
        assert config_long.timeouts.get_timeout_for_priority("P1 Medium") == 1800000    # 30m * 1.0

    def test_timeout_config_direct_instantiation(self):
        """Test TimeoutConfig behavior when instantiated directly."""
        # Without base_timeout_ms - uses defaults
        config_defaults = TimeoutConfig()
        assert config_defaults.get_timeout_for_priority("P0 Critical") == 900000
        assert config_defaults.get_timeout_for_priority("P1 Medium") == 600000

        # With base_timeout_ms - uses multipliers
        config_custom = TimeoutConfig(base_timeout_ms=120000)  # 2 minutes
        assert config_custom.get_timeout_for_priority("P0 Critical") == 180000  # 2m * 1.5
        assert config_custom.get_timeout_for_priority("P1 High") == 144000      # 2m * 1.2
        assert config_custom.get_timeout_for_priority("P1 Medium") == 120000    # 2m * 1.0
        assert config_custom.get_timeout_for_priority("P2 Low") == 120000       # 2m * 1.0

    def test_case_insensitive_priority_matching(self, tmp_path: Path):
        """Priority matching should be case insensitive."""
        config = ProcessorConfig(repo_root=tmp_path, timeout_ms=60000)

        # Various case combinations should work
        assert config.timeouts.get_timeout_for_priority("p0 critical") == 90000
        assert config.timeouts.get_timeout_for_priority("P0 CRITICAL") == 90000
        assert config.timeouts.get_timeout_for_priority("P0 Critical") == 90000
        assert config.timeouts.get_timeout_for_priority("P1 HIGH") == 72000
        assert config.timeouts.get_timeout_for_priority("p1 high") == 72000

    def test_partial_priority_matching(self, tmp_path: Path):
        """Should match priority substrings correctly."""
        config = ProcessorConfig(repo_root=tmp_path, timeout_ms=60000)

        # Just "p0" should match P0 Critical
        assert config.timeouts.get_timeout_for_priority("p0") == 90000

        # Just "critical" should match P0 Critical
        assert config.timeouts.get_timeout_for_priority("critical") == 90000

        # "p1" alone should match P1 Medium (not P1 High)
        assert config.timeouts.get_timeout_for_priority("p1") == 60000

        # "high" alone should match P1 High
        assert config.timeouts.get_timeout_for_priority("high") == 72000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
