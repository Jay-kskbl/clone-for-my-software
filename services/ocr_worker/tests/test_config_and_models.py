"""T17：配置读取、模型目录检查、模型名称与版本。"""

from pathlib import Path

import pytest

from ocr_worker.config import PROJECT_ROOT, ConfigError, load_settings, read_env_file
from ocr_worker.models import check_models

REQUIRED = {"DATABASE_URL": "postgresql://u:secret@db/x", "OPENSEARCH_URL": "http://os:9200"}


def test_defaults_point_at_the_project_model_directory():
    settings = load_settings(env_file=None, environ=REQUIRED)

    assert settings.ocr_det_model_dir == PROJECT_ROOT / "models/ocr/PP-OCRv5_mobile_det"
    assert settings.ocr_rec_model_dir == PROJECT_ROOT / "models/ocr/PP-OCRv5_mobile_rec"
    assert settings.storage_root == PROJECT_ROOT / "storage"
    assert (settings.ocr_pdf_dpi, settings.ocr_min_confidence) == (200, 0.0)


def test_missing_required_variables_are_listed_without_values():
    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=None, environ={"DATABASE_URL": "postgresql://u:secret@db/x"})

    assert "OPENSEARCH_URL" in str(excinfo.value)
    assert "secret" not in str(excinfo.value)


def test_invalid_values_are_reported_by_name():
    environ = {**REQUIRED, "OCR_PDF_DPI": "10", "OCR_MIN_CONFIDENCE": "2"}

    with pytest.raises(ConfigError) as excinfo:
        load_settings(env_file=None, environ=environ)

    assert "OCR_PDF_DPI" in str(excinfo.value)
    assert "OCR_MIN_CONFIDENCE" in str(excinfo.value)


def test_heartbeat_must_be_at_most_half_the_lease():
    environ = {**REQUIRED, "OCR_WORKER_LEASE_SECONDS": "10", "OCR_WORKER_HEARTBEAT_SECONDS": "6"}

    with pytest.raises(ConfigError, match="OCR_WORKER_HEARTBEAT_SECONDS"):
        load_settings(env_file=None, environ=environ)


def test_env_file_is_read_and_environment_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# 注释\n"
        "DATABASE_URL=postgresql://from-file/x\n"
        "OPENSEARCH_URL='http://from-file:9200'\n"
        "export OCR_PDF_DPI=150\n"
        "OPENSEARCH_INDEX_PREFIX=\n"
        "JWT_SECRET=irrelevant\n"
        "not a valid line\n",
        encoding="utf-8",
    )

    settings = load_settings(env_file=env_file, environ={"OCR_PDF_DPI": "300"})

    assert settings.database_url == "postgresql://from-file/x"
    assert settings.opensearch_url == "http://from-file:9200"
    assert settings.ocr_pdf_dpi == 300
    assert settings.opensearch_index_prefix == ""


def test_missing_env_file_is_fine(tmp_path):
    assert read_env_file(tmp_path / "none") == {}


def test_relative_paths_are_relative_to_the_project_root():
    settings = load_settings(env_file=None, environ={**REQUIRED, "OCR_DET_MODEL_DIR": "m/det"})

    assert settings.ocr_det_model_dir == PROJECT_ROOT / "m/det"


# ---- 模型目录 ----


def make_model(directory: Path, weights: bytes = b"weights") -> Path:
    directory.mkdir(parents=True)
    (directory / "inference.pdiparams").write_bytes(weights)
    (directory / "inference.yml").write_text("x: 1\n")
    (directory / "inference.json").write_text("{}")
    return directory


def test_complete_model_directories_pass_and_are_hashed(tmp_path):
    det = make_model(tmp_path / "PP-OCRv5_mobile_det", b"det")
    rec = make_model(tmp_path / "PP-OCRv5_mobile_rec", b"rec")

    info = check_models(det, rec)

    assert info.model_name == "PP-OCRv5_mobile_det+PP-OCRv5_mobile_rec"
    version = info.model_version("3.7.0")
    assert version.startswith("paddleocr-3.7.0/det-")
    assert len(version) <= 64
    assert info.det_sha256 != info.rec_sha256


def test_changing_the_weights_changes_the_version(tmp_path):
    rec = make_model(tmp_path / "rec")
    first = check_models(make_model(tmp_path / "det1", b"a"), rec).model_version("3.7.0")
    second = check_models(make_model(tmp_path / "det2", b"b"), rec).model_version("3.7.0")

    assert first != second


def test_missing_model_directory_is_a_config_error_not_a_download(tmp_path):
    rec = make_model(tmp_path / "rec")

    with pytest.raises(ConfigError, match="不会自动下载"):
        check_models(tmp_path / "nowhere", rec)


def test_incomplete_model_directory_names_the_missing_files(tmp_path):
    det = make_model(tmp_path / "det")
    rec = make_model(tmp_path / "rec")
    (rec / "inference.pdiparams").unlink()
    (rec / "inference.json").unlink()

    with pytest.raises(ConfigError) as excinfo:
        check_models(det, rec)

    assert "inference.pdiparams" in str(excinfo.value)
    assert "inference.json 或 inference.pdmodel" in str(excinfo.value)
