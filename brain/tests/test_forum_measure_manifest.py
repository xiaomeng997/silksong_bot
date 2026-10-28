"""Defaults are read from runtime bindings, never reinterpreted from env strings."""
from types import SimpleNamespace

from ssbot.train.forum_measure_manifest import configuration_manifest


def package(tmp_path, source):
    root = tmp_path / "ssbot"
    (root / "combat").mkdir(parents=True)
    (root / "combat" / "example.py").write_text(source)
    return root


def test_records_runtime_derived_defaults_and_source_without_importing(tmp_path):
    root = package(tmp_path, '''
import os
V2 = os.environ.get("SSBOT_FORUM_V2", "0") == "1"
ON = os.environ.get("SSBOT_FORUM_DERIVED", "1" if V2 else "0") == "1"
''')
    modules = {"ssbot.combat.example": SimpleNamespace(V2=True, ON=True)}
    result = configuration_manifest(root, modules=modules, environ={"SSBOT_FORUM_V2": "1"})
    derived = result["switches"]["SSBOT_FORUM_DERIVED"]
    assert derived["raw"] is None and not derived["present"]
    assert derived["bindings"]["ssbot.combat.example.ON"] is True
    assert result["configuration_complete"] and derived["sources"][0]["line"] == 4


def test_unresolved_active_read_blocks_configuration_certification(tmp_path):
    root = package(tmp_path, '''
def dynamic():
    return os.environ.get("SSBOT_FORUM_DYNAMIC", "0")
''')
    result = configuration_manifest(root, modules={"ssbot.combat.example": SimpleNamespace()}, environ={})
    assert result["unresolved"] == ["SSBOT_FORUM_DYNAMIC"]
    assert not result["configuration_complete"]


def test_module_not_imported_is_explicit_and_not_assigned_a_guessed_default(tmp_path):
    root = package(tmp_path, 'ON = os.environ.get("SSBOT_FORUM_UNUSED", "1") == "1"\n')
    result = configuration_manifest(root, modules={}, environ={})
    entry = result["switches"]["SSBOT_FORUM_UNUSED"]
    assert entry["resolution"] == "module_not_loaded" and not entry["bindings"]


def test_config_factory_dependency_resolves_to_the_constructed_config(tmp_path):
    root = package(tmp_path, '''
def config():
    return read_config("SSBOT_FORUM_SET")
CFG = config()
''')
    result = configuration_manifest(root, modules={"ssbot.combat.example": SimpleNamespace(CFG={"back_u": 6.0})},
                                    environ={"SSBOT_FORUM_SET": "back_u=6"})
    assert result["switches"]["SSBOT_FORUM_SET"]["bindings"] == {"ssbot.combat.example.CFG": {"back_u": 6.0}}
    assert result["configuration_complete"]


def test_key_name_alias_does_not_pretend_to_be_a_resolved_setting(tmp_path):
    root = package(tmp_path, 'ENV_NAME = "SSBOT_FORUM_ALIAS"\n')
    result = configuration_manifest(root, modules={"ssbot.combat.example": SimpleNamespace(ENV_NAME="SSBOT_FORUM_ALIAS")},
                                    environ={})
    assert result["unresolved"] == ["SSBOT_FORUM_ALIAS"]


def test_lazy_script_parameter_copy_preserves_identity_but_different_values_do_not(tmp_path, monkeypatch):
    from ssbot.train import forum_measure_manifest as fm
    root = package(tmp_path, "")
    configs = {"policy.params": {"hero2": True, "speed": 8.5}}
    monkeypatch.setattr(fm, "_config_objects", lambda policy: dict(configs))
    baseline = fm.configuration_manifest(root, modules={}, environ={})
    configs["policy.slam_play._csx.params"] = dict(configs["policy.params"])
    same = fm.configuration_manifest(root, modules={}, environ={})
    assert same["behavior_sha256"] == baseline["behavior_sha256"]
    assert "policy.slam_play._csx.params" in same["configs"]
    assert same["config_aliases"] == {"policy.slam_play._csx.params": "policy.params"}
    configs["policy.slam_play._csx.params"]["speed"] = 9.0
    different = fm.configuration_manifest(root, modules={}, environ={})
    assert different["behavior_sha256"] != baseline["behavior_sha256"]
    assert not different["config_aliases"]
