import random
from datetime import date

from app.modules.results.flags import evaluate_flag
from scripts.demo_values import numeric_value, value_for, values_for_test
from scripts.seed_demo_flow import (
    CatalogTest,
    describe_error,
    pick_test_codes,
    precondition_checks,
    read_env_file,
)

RANGE = {"low": 10.0, "high": 20.0, "critical_low": 5.0, "critical_high": 30.0}


def numeric(code="A", **extra):
    return {"code": code, "result_type": "numeric", "decimals": 1, **extra}


def test_numeric_normal_stays_inside_range():
    rand = random.Random(1)
    for _ in range(200):
        value = numeric_value(RANGE, 1, rand, abnormal=False)
        assert evaluate_flag(value, RANGE) == "normal"


def test_numeric_abnormal_gets_a_flag():
    rand = random.Random(2)
    flags = {
        evaluate_flag(numeric_value(RANGE, 1, rand, abnormal=True), RANGE)
        for _ in range(300)
    }
    assert "normal" not in flags
    assert {"low", "high"} <= flags


def test_numeric_one_sided_ranges_and_no_range():
    rand = random.Random(3)
    only_high = {"high": 5.0}
    only_low = {"low": 3.0}
    for _ in range(100):
        assert numeric_value(only_high, 2, rand, abnormal=False) <= 5.0
        assert numeric_value(only_high, 2, rand, abnormal=True) > 5.0
        assert numeric_value(only_low, 2, rand, abnormal=False) >= 3.0
        assert numeric_value(only_low, 2, rand, abnormal=True) < 3.0
    assert numeric_value(None, 0, rand, abnormal=True) >= 1


def test_value_for_types():
    rand = random.Random(4)
    assert (
        value_for(
            {"code": "C", "result_type": "calculated"}, "F", None, rand, abnormal=False
        )
        is None
    )
    expected = {"range": {"expected_boolean": True}}
    boolean = {"code": "B", "result_type": "boolean", **expected}
    assert value_for(boolean, "F", None, rand, abnormal=False) is True
    assert value_for(boolean, "F", None, rand, abnormal=True) is False
    options = [{"id": "o1"}, {"id": "o2", "is_abnormal": True}]
    qual = {
        "code": "Q",
        "result_type": "qualitative",
        "options": options,
        "range": {"expected_option_id": "o1"},
    }
    assert value_for(qual, "M", None, rand, abnormal=False) == "o1"
    assert value_for(qual, "M", None, rand, abnormal=True) == "o2"
    assert isinstance(
        value_for(
            {"code": "T", "result_type": "text"}, "M", None, rand, abnormal=False
        ),
        str,
    )


def test_values_for_test_fills_required_and_skips_calculated():
    analytes = [
        numeric("A", is_required=True, range=RANGE),
        {"code": "C", "result_type": "calculated"},
    ]
    values = values_for_test(analytes, "F", date(1990, 5, 5), random.Random(5))
    assert set(values) == {"A"}


def test_pick_test_codes_distinct_and_bounded():
    eligible = [CatalogTest(f"T{i}", f"Test {i}", "a") for i in range(10)]
    rand = random.Random(6)
    sizes = set()
    for _ in range(100):
        codes = pick_test_codes(eligible, rand)
        assert 1 <= len(codes) <= 4 and len(set(codes)) == len(codes)
        sizes.add(len(codes))
    assert sizes == {1, 2, 3, 4}


def test_precondition_checks_require_note_when_not_met():
    pre = [{"key": f"k{i}", "name": "Ayuno"} for i in range(200)]
    checks = precondition_checks(pre, random.Random(7), "toma")
    assert any(not c["met"] for c in checks)
    assert all(c["note"] for c in checks if not c["met"])
    assert all(c["note"] is None for c in checks if c["met"])


def test_read_env_file_and_describe_error(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# c\nA=1\nB='x y'\n", encoding="utf-8")
    assert read_env_file(env) == {"A": "1", "B": "x y"}
    assert read_env_file(tmp_path / "nope") == {}

    class Fake:
        status_code = 409

        @staticmethod
        def json():
            return {"code": "conflict", "message": "Ya existe."}

    assert "Ya existe." in describe_error("POST", "/x", Fake())
