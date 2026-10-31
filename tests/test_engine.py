"""Automated validation, deterministic-protocol and real-Prolog acceptance tests."""
import json
import re
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from loanwise.engine import (
    ExpertSystemError, RULES_PATH, assess, engine_available, rule_catalog,
    sample_case, validate_case,
)


def test_rule_counts_are_source_grounded():
    rules = rule_catalog()
    ids = [r["id"] for r in rules]
    assert len(rules) == 68, f"Expected exactly 68 intentional clauses, got {len(rules)}"
    assert len(ids) == len(set(ids)), "Every inference clause must have a unique ID"
    assert {f"D{n:02d}" for n in range(1, 8)} <= set(ids)
    assert len([r for r in rules if r["category"] != "decision"]) == 61
    # All 61 nondecision rules include a Prolog condition body.
    source = RULES_PATH.read_text(encoding="utf8")
    assert len(re.findall(r"^rule\([^\n]+:-", source, re.MULTILINE)) == 62 # + one dispatch rule
    assert "decision(C, _, rejected" in source
    assert "decision(_, _, approved" in source


def test_sample_profiles_follow_schema():
    for preset in ("strong", "borderline", "high_risk"):
        assert validate_case(sample_case(preset))


@pytest.mark.parametrize("key,value", [
    ("loan_type", "'personal');halt."),
    ("employment", "hacker"),
    ("age", 17),
    ("credit_score", 900),
    ("income", float("inf")),
    ("amount", -5),
    ("recent_default", "false"),
    ("term", 36.4),
    ("bank_statements", 1),
])
def test_rejects_malformed_fields(key, value):
    case = sample_case()
    case[key] = value
    with pytest.raises(ExpertSystemError):
        validate_case(case)


def test_rejects_unknown_fields():
    case = sample_case()
    case["internal_admin_flag"] = True
    with pytest.raises(ExpertSystemError):
        validate_case(case)


def test_fails_closed_without_prolog():
    with patch("loanwise.engine.shutil.which", return_value=None):
        with pytest.raises(ExpertSystemError, match="SWI-Prolog"):
            assess(sample_case())


def test_bridge_reads_prolog_result_without_python_decision_logic():
    payload = {"decision":"approved", "decision_rule":"D07", "rules":[{"id":"D07"}]}
    completed = MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("loanwise.engine.shutil.which", return_value="/usr/bin/swipl"), \
         patch("loanwise.engine.subprocess.run", return_value=completed) as command:
        result = assess(sample_case())
        assert result == payload
        args = command.call_args
        assert args.args[0][0] == "swipl"
        assert "shell" not in args.kwargs  # shell execution not used
        assert json.loads(args.kwargs["input"])["loan_type"] == "personal"


@pytest.mark.skipif(not engine_available(), reason="SWI-Prolog must be installed to run real inference tests")
class TestPrologEndToEnd:
    def test_approval_and_evidence(self):
        result = assess(sample_case("strong"))
        assert result["decision"] == "approved"
        assert result["decision_rule"] == "D07"
        assert result["risk_score"] >= 80
        assert 0 < result["metrics"]["dti"] < 40
        ids = {r["id"] for r in result["rules"]}
        assert {"B03", "B07", "C02", "D07"} <= ids

    def test_manual_review_is_a_distinct_expert_decision(self):
        result = assess(sample_case("borderline"))
        assert result["decision"] == "manual_review"
        assert result["decision_rule"] == "D05"
        assert "B06" in {r["id"] for r in result["rules"]}

    def test_default_rejects_with_prioritized_rule(self):
        result = assess(sample_case("high_risk"))
        assert result["decision"] == "rejected"
        assert result["decision_rule"] == "D02"
        assert "R05" in {r["id"] for r in result["rules"]}

    def test_age_precedes_credit_rejection(self):
        case = sample_case("high_risk")
        case["age"] = 19
        result = assess(case)
        assert result["decision_rule"] == "D01"

    def test_debt_burden_rejection(self):
        case = sample_case()
        case["debt"] = 160_000
        result = assess(case)
        assert result["decision_rule"] == "D03"

    def test_product_tenure_constraints(self):
        case = sample_case()
        case["loan_type"] = "home"
        case["term"] = 36
        case["collateral"] = 2_000_000
        result = assess(case)
        assert result["decision_rule"] == "D04"
        assert "L07" in {r["id"] for r in result["rules"]}

    def test_down_payment_manual_review(self):
        case = sample_case()
        case.update(loan_type="car", collateral=900_000, amount=800_000)
        result = assess(case)
        assert result["decision_rule"] == "D05"
        assert "L04" in {r["id"] for r in result["rules"]}

    def test_missing_document_review(self):
        case = sample_case()
        case["income_proof"] = False
        assert assess(case)["decision_rule"] == "D05"

    def test_triggered_rule_ids_are_unique_and_known(self):
        case = sample_case()
        rules = assess(case)["rules"]
        ids = [r["id"] for r in rules]
        assert len(ids) == len(set(ids))
        assert set(ids) <= {r["id"] for r in rule_catalog()}
