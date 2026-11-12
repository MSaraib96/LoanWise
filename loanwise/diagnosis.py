"""Group the rules Prolog has fired into a diagnosis: problem areas, evidence and remedies.

This is presentation logic only. It regroups critical/warning findings and improvement
rules that the knowledge base already fired for this applicant; it never adds a finding
or a remedy of its own, so the diagnosis stays traceable to Prolog rule IDs.
"""
from __future__ import annotations

# (rule module, label shown to the user, improvement rules that address that area)
AREAS = (
    ("credit", "Credit and payment history", ("I04",)),
    ("affordability", "Affordability and repayment", ("I01", "I02", "I03")),
    ("employment", "Employment and stability", ()),
    ("product", "Loan product policy", ("I06",)),
    ("basic", "Eligibility and documents", ("I05",)),
    ("risk", "Overall risk and reserves", ("I07",)),
)
PROBLEM_LEVELS = ("critical", "warning")


def diagnose(result: dict) -> list[dict]:
    """Return problem areas, most serious first.

    Each item has the area label, its worst severity, the fired findings (rule dicts)
    and the improvement rules, fired for this applicant, that address the area.
    """
    rules = result["rules"]
    fired = {r["id"]: r for r in rules}
    findings = []
    for category, label, remedy_ids in AREAS:
        issues = [r for r in rules if r["category"] == category and r["severity"] in PROBLEM_LEVELS]
        if not issues:
            continue
        findings.append({
            "area": label,
            "severity": "critical" if any(r["severity"] == "critical" for r in issues) else "warning",
            "issues": issues,
            "remedies": [fired[i] for i in remedy_ids if i in fired],
        })
    findings.sort(key=lambda f: (f["severity"] != "critical", -len(f["issues"])))
    return findings
