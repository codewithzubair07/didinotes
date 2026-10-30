from pathlib import Path

import pytest

from app.config_loader import ConfigError, load_incentives, load_lexicon

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def test_sample_incentives_load_with_null_amounts():
    tasks = load_incentives(CONFIG_DIR / "incentives.yaml")
    assert len(tasks) == 6
    assert all(task.incentive_inr is None and task.verified is False for task in tasks)


def test_amount_without_verification_fails_loudly(tmp_path):
    bad = tmp_path / "incentives.yaml"
    bad.write_text(
        "task_types:\n"
        "  - id: x\n"
        "    bn_label: a\n"
        "    en_label: b\n"
        "    required_documents: [doc]\n"
        "    incentive_inr: 500\n"
        "    verified: false\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="verified is false"):
        load_incentives(bad)


def test_missing_config_fails_loudly(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_incentives(tmp_path / "missing.yaml")


def test_lexicon_loads():
    lexicon = load_lexicon(CONFIG_DIR / "lexicon.yaml")
    assert lexicon.number_words[2] == ["dui", "দুই"]
