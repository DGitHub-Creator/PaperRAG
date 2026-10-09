"""配置层安全门禁（A0-3 ④⑤⑧）。"""

from unittest.mock import patch

import pytest

from backend.core.config import env_presets, validate_runtime_security


class TestRuntimeSecurityFailFast:
    def test_missing_jwt_secret_raises_in_development(self):
        with (
            patch("backend.core.config.JWT_SECRET_KEY", ""),
            patch("backend.core.config.is_production", return_value=False),
        ):
            with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
                validate_runtime_security()

    def test_missing_jwt_secret_raises_in_production(self):
        with (
            patch("backend.core.config.JWT_SECRET_KEY", ""),
            patch("backend.core.config.is_production", return_value=True),
        ):
            with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
                validate_runtime_security()

    def test_leftover_placeholder_secret_is_still_flagged(self):
        with (
            patch("backend.core.config.JWT_SECRET_KEY", "replace-with-strong-random-secret"),
            patch("backend.core.config.is_production", return_value=True),
        ):
            with pytest.raises(RuntimeError, match="placeholder"):
                validate_runtime_security()

    @pytest.mark.parametrize("leaked", ["paperrag-admin-2026", "researchpilot-admin-2026"])
    def test_non_jwt_issues_only_warn_in_development(self, leaked):
        """两个项目名的弱默认口令都要拒：改名不能把已暴露过的值重新变成可用值。"""
        with (
            patch("backend.core.config.JWT_SECRET_KEY", "a-real-secret"),
            patch("backend.core.config.ADMIN_INVITE_CODE", leaked),
            patch("backend.core.config.is_production", return_value=False),
            patch("backend.core.config.logger") as mock_logger,
        ):
            validate_runtime_security()
            assert mock_logger.warning.called

    def test_unset_invite_code_is_reported_as_admin_disabled(self):
        with (
            patch("backend.core.config.JWT_SECRET_KEY", "a-real-secret"),
            patch("backend.core.config.ADMIN_INVITE_CODE", ""),
            patch("backend.core.config.ALLOWED_ORIGINS", ["https://example.com"]),
            patch("backend.core.config.is_production", return_value=False),
            patch("backend.core.config.logger") as mock_logger,
        ):
            validate_runtime_security()
            assert mock_logger.info.called


class TestEnvPresets:
    def test_production_enables_global_rate_limit(self):
        assert env_presets("production")["RATE_LIMIT"] == "60/minute"
        assert env_presets("prod")["RATE_LIMIT"] == "60/minute"

    def test_development_enables_nothing(self):
        """开发环境不启用全局限流，避免打断本地上传轮询与测试。"""
        assert env_presets("development") == {}
        assert env_presets("") == {}
