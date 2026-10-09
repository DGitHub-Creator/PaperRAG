"""测试分层机检（P0-0 X7）：marker 注册与目录约定都由断言保证，不靠文档口径。"""

import tomllib
from pathlib import Path

from tests.conftest import layer_for

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ("unit", "integration", "chain", "e2e", "slow")


class TestMarkerRegistration:
    def test_all_layers_registered(self):
        ini = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
        registered = "\n".join(ini["markers"])
        for layer in LAYERS:
            assert f"{layer}:" in registered, f"marker {layer} 未注册，--strict-markers 下用到即报错"

    def test_strict_markers_is_on(self):
        ini = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
        assert "--strict-markers" in ini["addopts"]


class TestLayerFor:
    def test_dir_names_map_to_own_layer(self):
        assert layer_for("unit", "test_auth.py") == "unit"
        assert layer_for("integration", "test_api.py") == "integration"
        assert layer_for("chain", "test_contract.py") == "chain"
        assert layer_for("e2e", "test_upload.py") == "e2e"

    def test_root_tests_default_to_unit_except_app_level(self):
        assert layer_for("", "test_verify.py") == "unit"
        assert layer_for("", "test_health.py") == "integration"

    def test_unknown_dir_falls_back_to_unit(self):
        assert layer_for("fixtures", "test_x.py") == "unit"
