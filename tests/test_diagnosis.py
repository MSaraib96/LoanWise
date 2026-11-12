import pytest

from loanwise.diagnosis import diagnose
from loanwise.engine import assess, engine_available, sample_case


def rule(rule_id, category, severity, text="finding"):
    return {"id": rule_id, "category": category, "severity": severity, "explanation": text}


def test_positive_and_info_rules_are_not_problems():
    result = {"rules": [rule("C02", "credit", "positive"), rule("A03", "affordability", "info")]}
    assert diagnose(result) == []


def test_decision_and_improvement_rules_are_never_findings():
    result = {"rules": [rule("D02", "decision", "priority"), rule("I01", "improvement", "info")]}
    assert diagnose(result) == []


def test_findings_are_grouped_by_area_and_critical_areas_come_first():
    result = {"rules": [
        rule("A04", "affordability", "warning"),
        rule("A05", "affordability", "warning"),
        rule("C07", "credit", "critical"),
        rule("E03", "employment", "warning"),
    ]}
    areas = diagnose(result)
    assert [a["area"] for a in areas] == [
        "Credit and payment history", "Affordability and repayment", "Employment and stability"]
    assert [a["severity"] for a in areas] == ["critical", "warning", "warning"]
    assert [i["id"] for i in areas[1]["issues"]] == ["A04", "A05"]


def test_remedy_is_only_offered_when_its_improvement_rule_fired():
    problem = rule("A04", "affordability", "warning")
    without = diagnose({"rules": [problem]})[0]
    assert without["remedies"] == []
    with_fix = diagnose({"rules": [problem, rule("I01", "improvement", "info"), rule("I04", "improvement", "info")]})[0]
    assert [r["id"] for r in with_fix["remedies"]] == ["I01"]  # I04 belongs to the credit area


@pytest.mark.skipif(not engine_available(), reason="SWI-Prolog must be installed to run real inference tests")
class TestDiagnosisWithRealProlog:
    def test_strong_profile_has_no_critical_findings(self):
        findings = diagnose(assess(sample_case("strong")))
        assert all(f["severity"] != "critical" for f in findings)

    def test_high_risk_profile_is_diagnosed_from_fired_rules_only(self):
        result = assess(sample_case("high_risk"))
        findings = diagnose(result)
        fired_ids = {r["id"] for r in result["rules"]}
        assert findings and findings[0]["severity"] == "critical"
        for finding in findings:
            assert {i["id"] for i in finding["issues"]} <= fired_ids
            assert {r["id"] for r in finding["remedies"]} <= fired_ids
