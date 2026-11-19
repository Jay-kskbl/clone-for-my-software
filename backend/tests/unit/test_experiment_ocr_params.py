"""T24c：实验记录里的 OCR 参数——汇总和“参数没有记录或不一致”的判断（D42）。

只测纯函数，不需要数据库；从数据库读出分组的部分在
tests/integration/test_experiments_db.py。
"""

import json

from app.modules.experiments.__main__ import ocr_param_problems, ocr_params_summary

PAGE = {"pdf_dpi": 200, "min_confidence": 0.5, "max_pixels": 100_000_000}
IMAGE = {"pdf_dpi": None, "min_confidence": 0.5, "max_pixels": 100_000_000}


def test_consistent_params_have_no_problems():
    assert ocr_param_problems([(PAGE, 10)]) == []


def test_images_without_dpi_do_not_conflict_with_pdf_pages():
    # 独立图片不渲染，pdf_dpi 为 None，不算与 PDF 页的 200 不一致
    assert ocr_param_problems([(PAGE, 10), (IMAGE, 3)]) == []


def test_no_ocr_results_has_no_problems():
    assert ocr_param_problems([]) == []


def test_unrecorded_results_are_reported_with_their_count():
    problems = ocr_param_problems([(PAGE, 10), ({}, 4)])

    assert len(problems) == 1
    assert "4 条 OCR 结果没有记录识别参数" in problems[0]


def test_each_differing_parameter_is_reported_once():
    rows = [
        (PAGE, 5),
        ({**PAGE, "pdf_dpi": 300}, 2),
        ({**IMAGE, "min_confidence": 0.8}, 1),
    ]

    problems = ocr_param_problems(rows)

    assert len(problems) == 2
    assert "pdf_dpi" in problems[0] and "[200, 300]" in problems[0]
    assert "min_confidence" in problems[1] and "0.5" in problems[1] and "0.8" in problems[1]


def test_images_alone_with_different_settings_are_still_reported():
    problems = ocr_param_problems([(IMAGE, 2), ({**IMAGE, "max_pixels": 5}, 1)])

    assert len(problems) == 1 and "max_pixels" in problems[0]


def test_summary_is_sorted_by_count_and_json_serializable():
    summary = ocr_params_summary([(IMAGE, 1), (PAGE, 7), ({}, 1)])

    assert [item["results"] for item in summary] == [7, 1, 1]
    assert summary[0] == {"params": PAGE, "results": 7}
    # 条数相同时顺序固定，config.json 每次一样
    assert summary == ocr_params_summary([({}, 1), (PAGE, 7), (IMAGE, 1)])
    assert json.loads(json.dumps(summary)) == summary
