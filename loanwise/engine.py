"""Safe, deterministic JSON subprocess bridge to the SWI-Prolog expert system.

No Python code makes or changes an eligibility decision. All inferences,
financial metrics, score components, recommendations and rule traces originate
in the SWI-Prolog knowledge base.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[1] / "prolog" / "loanwise.pl"
LOAN_TYPES = {"personal", "car", "home"}
EMPLOYMENT_TYPES = {"salaried", "self_employed", "contract", "unemployed"}
REQUIRED = {
    "age", "income", "debt", "credit_score", "employment", "years_employed",
    "amount", "term", "loan_type", "has_id", "income_proof",
    "bank_statements", "recent_default", "late_payments", "collateral", "savings",
}

class ExpertSystemError(RuntimeError):
    """Validation, installation, protocol, or Prolog inference failure."""


def engine_available() -> bool:
    return bool(shutil.which(os.environ.get("SWIPL_BIN", "swipl")))


def validate_case(case: dict[str, Any]) -> dict[str, Any]:
    """Exact input schema prevents query injection and unrealistic numeric sizes."""
    if not isinstance(case, dict):
        raise ExpertSystemError("The application must be an object.")
    if set(case) != REQUIRED:
        missing = sorted(REQUIRED - set(case))
        extras = sorted(set(case) - REQUIRED)
        raise ExpertSystemError(f"Invalid applicant fields. Missing: {missing}; unexpected: {extras}.")
    values = dict(case)
    for key in ("has_id", "income_proof", "bank_statements", "recent_default"):
        if type(values[key]) is not bool:
            raise ExpertSystemError(f"{key} must be a boolean.")
    for key, allowed in (("loan_type", LOAN_TYPES), ("employment", EMPLOYMENT_TYPES)):
        if not isinstance(values[key], str) or values[key] not in allowed:
            raise ExpertSystemError(f"{key} must be one of {', '.join(sorted(allowed))}.")
    boundaries = {
        "age": (18, 90), "income": (0, 10_000_000), "debt": (0, 10_000_000),
        "credit_score": (300, 850), "years_employed": (0, 60),
        "amount": (1, 50_000_000), "term": (6, 360),
        "late_payments": (0, 12), "collateral": (0, 100_000_000),
        "savings": (0, 100_000_000),
    }
    whole = {"age", "credit_score", "term", "late_payments"}
    for key, (minimum, maximum) in boundaries.items():
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ExpertSystemError(f"{key} must be a finite number.")
        if key in whole and int(value) != value:
            raise ExpertSystemError(f"{key} must be a whole number.")
        if not minimum <= value <= maximum:
            raise ExpertSystemError(f"{key} must be between {minimum:,} and {maximum:,}.")
        values[key] = int(value) if key in whole else float(value)
    return values


def assess(case: dict[str, Any]) -> dict[str, Any]:
    """Run the actual Prolog knowledge base; fail closed if unavailable."""
    payload = validate_case(case)
    executable = os.environ.get("SWIPL_BIN", "swipl")
    if not shutil.which(executable):
        raise ExpertSystemError(
            "SWI-Prolog is not installed or available on PATH. Install SWI-Prolog "
            "and restart Streamlit; the system will not substitute Python decisions."
        )
    try:
        process = subprocess.run(
            [executable, "-q", "-f", "none", "-s", str(RULES_PATH), "-g", "main", "-t", "halt"],
            input=json.dumps(payload, allow_nan=False),
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
            cwd=str(RULES_PATH.parent),
            env={**os.environ, "LANG": "C.UTF-8"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ExpertSystemError("The Prolog engine timed out.") from exc
    except OSError as exc:
        raise ExpertSystemError(f"Unable to launch SWI-Prolog: {exc}") from exc
    try:
        result = json.loads(process.stdout.strip())
    except (json.JSONDecodeError, TypeError) as exc:
        raise ExpertSystemError(
            f"Prolog returned invalid data. {process.stderr.strip()[:400]}"
        ) from exc
    if process.returncode != 0 or not isinstance(result, dict) or "error" in result:
        raise ExpertSystemError(f"Prolog inference failed: {result.get('error', process.stderr.strip())}")
    if result.get("decision") not in {"approved", "rejected", "manual_review"}:
        raise ExpertSystemError("Prolog returned an unknown decision.")
    if not isinstance(result.get("rules"), list) or not result.get("decision_rule"):
        raise ExpertSystemError("Prolog returned no proof trace.")
    return result


def sample_case(kind: str = "strong") -> dict[str, Any]:
    """Synthetic applicants; all numbers and policies are fictional."""
    base: dict[str, Any] = {
        "age": 34, "income": 200_000, "debt": 15_000,
        "credit_score": 785, "employment": "salaried", "years_employed": 6.0,
        "amount": 800_000, "term": 36, "loan_type": "personal",
        "has_id": True, "income_proof": True, "bank_statements": True,
        "recent_default": False, "late_payments": 0,
        "collateral": 0.0, "savings": 700_000,
    }
    if kind == "borderline":
        base.update(income=135_000, debt=30_000, credit_score=648,
                    amount=1_000_000, years_employed=1.5, savings=80_000,
                    bank_statements=False, late_payments=1)
    elif kind == "high_risk":
        base.update(income=70_000, debt=40_000, credit_score=480,
                    amount=1_400_000, years_employed=0.5, savings=5_000,
                    recent_default=True, late_payments=5)
    elif kind != "strong":
        raise ValueError(f"Unknown synthetic case: {kind}")
    return base


def money(amount: float, compact: bool = False) -> str:
    if compact and abs(amount) >= 1_000_000:
        return f"PKR {amount/1_000_000:,.2f}M"
    if compact and abs(amount) >= 1_000:
        return f"PKR {amount/1_000:,.1f}K"
    return f"PKR {amount:,.0f}"


def rule_catalog() -> list[dict[str, str]]:
    """Parse documentation of the real clauses, never fabricate a rule tally."""
    import re
    source = RULES_PATH.read_text(encoding="utf-8")
    regex = re.compile(
        r"^rule\([^\n]*?'([BECLARI]\d{2})',\s*(\w+),\s*(\w+),\s*'([^']+)'\)\s*:-",
        re.MULTILINE,
    )
    rules = [dict(id=m.group(1), category=m.group(2), severity=m.group(3),
                  explanation=m.group(4)) for m in regex.finditer(source)]
    # Seven Dxx clauses are real inference predicates, with their own gates.
    for match in re.finditer(
        r"^decision\([^\n]+?\s*'D(\d{2})',\s*'([^']+)'\)\s*(?::-|\.)",
        source, re.MULTILINE,
    ):
        rules.append(dict(id="D" + match.group(1), category="decision",
                          severity="priority", explanation=match.group(2)))
    return sorted(rules, key=lambda r: (r["id"][0], r["id"]))
