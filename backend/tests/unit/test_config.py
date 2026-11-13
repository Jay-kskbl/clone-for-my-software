"""T01 🧪：缺失必填配置时启动失败且错误信息明确。"""

import pytest

from app.config import PROJECT_ROOT, load_settings
from app.core.errors import ConfigError
from app.main import create_app

REQUIRED = {
    "DATABASE_URL": "postgresql://u:secret-pw@localhost:5432/db",
    "OPENSEARCH_URL": "http://localhost:9200",
    "CLIP_SERVICE_URL": "http://localhost:8001",
}


@pytest.fixture
def clean_env(monkeypatch):
    for name in [*REQUIRED, "HEALTH_CHECK_TIMEOUT_SECONDS", "STORAGE_ROOT"]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_loads_when_all_required_present(clean_env):
    for name, value in REQUIRED.items():
        clean_env.setenv(name, value)

    settings = load_settings(env_file=None)

    assert settings.database_url == REQUIRED["DATABASE_URL"]
    assert settings.health_check_timeout_seconds == 2.0


@pytest.mark.parametrize("missing", list(REQUIRED))
def test_each_missing_required_var_is_named(clean_env, missing):
    for name, value in REQUIRED.items():
        if name != missing:
            clean_env.setenv(name, value)

    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=None)

    message = str(excinfo.value)
    assert missing in message
    assert ".env.example" in message
    # 没缺的变量不应被误报
    for name in REQUIRED:
        if name != missing:
            assert name not in message


def test_all_missing_vars_listed_together(clean_env):
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=None)

    for name in REQUIRED:
        assert name in str(excinfo.value)


def test_empty_value_is_rejected(clean_env):
    for name, value in REQUIRED.items():
        clean_env.setenv(name, value)
    clean_env.setenv("OPENSEARCH_URL", "")

    with pytest.raises(ConfigError, match="OPENSEARCH_URL"):
        load_settings(env_file=None)


def test_invalid_value_error_does_not_leak_secrets(clean_env):
    for name, value in REQUIRED.items():
        clean_env.setenv(name, value)
    clean_env.setenv("HEALTH_CHECK_TIMEOUT_SECONDS", "-1")

    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=None)

    assert "HEALTH_CHECK_TIMEOUT_SECONDS" in str(excinfo.value)
    assert "secret-pw" not in str(excinfo.value)


def test_reads_env_file(clean_env, tmp_path):
    env_file = tmp_path / ".env"
    lines = [f"{k}={v}" for k, v in REQUIRED.items()]
    lines.append("POSTGRES_USER=ignored-by-backend")
    env_file.write_text("\n".join(lines), encoding="utf-8")

    settings = load_settings(env_file=env_file)

    assert settings.clip_service_url == REQUIRED["CLIP_SERVICE_URL"]


def test_app_startup_fails_with_readable_message(clean_env, capsys, monkeypatch, tmp_path):
    # 指向一个不存在的 .env，保证测试不受开发机上真实 .env 的影响
    monkeypatch.setattr("app.config.DEFAULT_ENV_FILE", tmp_path / "no-such.env")
    monkeypatch.setattr(
        "app.main.load_settings", lambda: load_settings(env_file=tmp_path / "no-such.env")
    )

    with pytest.raises(SystemExit) as excinfo:
        create_app()

    assert excinfo.value.code == 1
    stderr = capsys.readouterr().err
    assert "缺少必填环境变量" in stderr
    assert "DATABASE_URL" in stderr


def test_storage_root_defaults_to_project_storage_dir(clean_env):
    for name, value in REQUIRED.items():
        clean_env.setenv(name, value)
    clean_env.delenv("STORAGE_ROOT", raising=False)

    assert load_settings(env_file=None).storage_root == PROJECT_ROOT / "storage"


def test_relative_storage_root_resolved_against_project_root(clean_env):
    for name, value in REQUIRED.items():
        clean_env.setenv(name, value)
    clean_env.setenv("STORAGE_ROOT", "data/files")

    assert load_settings(env_file=None).storage_root == PROJECT_ROOT / "data" / "files"


def test_absolute_storage_root_kept(clean_env, tmp_path):
    for name, value in REQUIRED.items():
        clean_env.setenv(name, value)
    clean_env.setenv("STORAGE_ROOT", str(tmp_path))

    assert load_settings(env_file=None).storage_root == tmp_path
