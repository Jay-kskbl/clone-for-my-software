"""配置读取、权重文件检查、模型版本字符串。"""

import hashlib

import pytest

from clip_service.config import (
    DEFAULT_MODEL_PATH,
    PROJECT_ROOT,
    ConfigError,
    load_settings,
    read_env_file,
)
from clip_service.models import check_model_file, file_sha256, make_model_version


def _load(**environ: str):
    return load_settings(env_file=None, environ=environ)


def test_defaults_need_no_variables():
    settings = _load()
    assert settings.clip_model_path == DEFAULT_MODEL_PATH
    assert settings.clip_model_name == "ViT-B-16"
    assert settings.clip_model_sha256 is None
    assert settings.clip_device == "cpu"
    assert settings.clip_host == "127.0.0.1"
    assert settings.clip_port == 8001


def test_relative_model_path_is_resolved_against_project_root():
    settings = _load(CLIP_MODEL_PATH="models/clip/other.pt")
    assert settings.clip_model_path == PROJECT_ROOT / "models" / "clip" / "other.pt"


def test_names_are_case_insensitive_and_empty_means_unset():
    settings = _load(clip_port="9000", CLIP_MODEL_SHA256="", CLIP_DEVICE="")
    assert settings.clip_port == 9000
    assert settings.clip_model_sha256 is None
    assert settings.clip_device == "cpu"


def test_sha256_is_lowercased():
    settings = _load(CLIP_MODEL_SHA256="AB" * 32)
    assert settings.clip_model_sha256 == "ab" * 32


def test_unrelated_variables_are_ignored():
    settings = _load(DATABASE_URL="postgresql://x/y", JWT_SECRET="s", CLIP_PORT="8002")
    assert settings.clip_port == 8002


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("CLIP_DEVICE", "gpu"),
        ("CLIP_PORT", "0"),
        ("CLIP_PORT", "abc"),
        ("CLIP_MODEL_SHA256", "1234"),
        ("CLIP_MAX_IMAGE_BYTES", "0"),
        ("CLIP_MAX_IMAGE_PIXELS", "-1"),
        ("CLIP_MAX_TEXTS", "0"),
        ("CLIP_MAX_TEXT_CHARS", "0"),
    ],
)
def test_invalid_value_names_the_variable_without_echoing_it(name, value):
    with pytest.raises(ConfigError) as excinfo:
        _load(**{name: value})
    message = str(excinfo.value)
    assert name in message
    assert f"={value}" not in message


def test_env_file_is_read_and_environment_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# 注释\nCLIP_PORT=8100\nexport CLIP_DEVICE='cpu'\nCLIP_MAX_TEXTS=\"8\"\n\n",
        encoding="utf-8",
    )
    assert read_env_file(env_file) == {
        "CLIP_PORT": "8100",
        "CLIP_DEVICE": "cpu",
        "CLIP_MAX_TEXTS": "8",
    }
    settings = load_settings(env_file=env_file, environ={"CLIP_PORT": "8200"})
    assert settings.clip_port == 8200
    assert settings.clip_max_texts == 8


def test_missing_env_file_is_fine(tmp_path):
    assert read_env_file(tmp_path / "nope.env") == {}


# ---- 权重文件 ----


def test_missing_model_file_is_a_config_error_and_mentions_no_download(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        check_model_file(tmp_path / "missing.pt")
    assert "找不到模型权重文件" in str(excinfo.value)
    assert "不会联网下载" in str(excinfo.value)


def test_a_directory_is_not_a_model_file(tmp_path):
    with pytest.raises(ConfigError):
        check_model_file(tmp_path)


def test_check_returns_the_file_hash(tmp_path):
    path = tmp_path / "w.pt"
    content = b"weights" * 300_000  # 超过一个读取块
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert file_sha256(path) == expected
    assert check_model_file(path) == expected
    assert check_model_file(path, expected) == expected


def test_hash_mismatch_refuses_to_start(tmp_path):
    path = tmp_path / "w.pt"
    path.write_bytes(b"weights")
    with pytest.raises(ConfigError) as excinfo:
        check_model_file(path, "0" * 64)
    assert "sha256" in str(excinfo.value)


def test_model_version_changes_with_library_or_weights():
    sha_a, sha_b = "a" * 64, "b" * 64
    assert make_model_version("1.6.0", sha_a) == "cn_clip-1.6.0-aaaaaaaaaaaa"
    assert make_model_version("1.6.0", sha_a) != make_model_version("1.6.0", sha_b)
    assert make_model_version("1.6.0", sha_a) != make_model_version("1.7.0", sha_a)
    assert make_model_version("", sha_a) == "cn_clip-unknown-aaaaaaaaaaaa"
    # image_embeddings.model_version 是 varchar(64)
    assert len(make_model_version("9" * 200, sha_a)) <= 64
