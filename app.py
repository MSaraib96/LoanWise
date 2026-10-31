"""LoanWise — SWI-Prolog powered decision support and decision making studio.

Start: streamlit run app.py
Model is a fictional educational policy system; not for real lending decisions.
"""
from __future__ import annotations

from collections import Counter
import html
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from loanwise.engine import (
    ExpertSystemError, assess, engine_available, money, rule_catalog, sample_case,
)

st.set_page_config(
    page_title="LoanWise | Expert Decision Intelligence",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "LoanWise: a fictional, rule-based loan assessment expert system."},
)
st.markdown(f"<style>{(Path(__file__).parent / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def esc(x: object) -> str:
    return html.escape(str(x), quote=True)


def section(title: str, subtitle: str = "", overline: str = "") -> None:
    st.markdown(f'<div class="lw-section"><div><div class="lw-overline">{esc(overline)}</div>'
                f'<h2>{esc(title)}</h2><p>{esc(subtitle)}</p></div></div>', unsafe_allow_html=True)


def empty(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="lw-empty"><strong>{esc(title)}</strong><p>{esc(subtitle)}</p></div>', unsafe_allow_html=True)


def money_short(amount: float) -> str:
    return money(amount, compact=True)


def kpi_row(items: list[tuple[str, str, str]]) -> None:
    cards = "".join(
        f'<div class="lw-kpi"><div class="lbl">{esc(label)}</div>'
        f'<div class="val">{esc(value)}</div><div class="sub">{esc(caption)}</div></div>'
        for label, value, caption in items
    )
    st.markdown(f'<div class="lw-kpis">{cards}</div>', unsafe_allow_html=True)


def decision_name(decision: str) -> str:
    return {"approved": "Approved", "manual_review": "Manual review", "rejected": "Rejected"}.get(decision, decision)


def decision_banner(result: dict) -> None:
    decision = result["decision"]
    label = decision_name(decision)
    reason = result["decision_reason"]
    st.markdown(
        f'<div class="lw-banner"><div>'
        f'<div class="lw-overline">EXPERT SYSTEM / FINAL INFERENCE</div>'
        f'<div class="big">{esc(label)}</div>'
        f'<div class="little">{esc(reason)}</div></div>'
        f'<div class="lw-tag {esc(decision)}">{esc(result["decision_rule"])} · {esc(label)}</div></div>',
        unsafe_allow_html=True,
    )


def score_chart(scores: dict) -> go.Figure:
    labels = ["Credit quality", "Affordability", "Employment", "Payment history", "Loan security", "Documentation"]
    keys = ["credit", "affordability", "employment", "history", "security", "documents"]
    values = [scores[key] for key in keys]
    colors = ["#BDF38B" if value >= 80 else "#F2C477" if value >= 60 else "#E58F98" for value in values]
    fig = go.Figure(go.Bar(x=values[::-1], y=labels[::-1], orientation="h",
                           text=[f"{n}/100" for n in values[::-1]], textposition="outside",
                           marker=dict(color=colors[::-1], line=dict(width=0))))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="DM Sans, Arial", color="#B6C6D8", size=13),
                      margin=dict(l=5, r=52, t=12, b=5), height=315, showlegend=False,
                      xaxis=dict(range=[0, 112], showticklabels=False, showgrid=True,
                                 gridcolor="#29374A", zeroline=False),
                      yaxis=dict(showgrid=False, tickfont=dict(size=13)))
    return fig


def affordability_chart(case: dict, result: dict) -> go.Figure:
    m = result["metrics"]
    debt = case["debt"]
    emi = m["emi"]
    available = max(0, case["income"] - debt - emi)
    fig = go.Figure(go.Pie(labels=["Existing debt", "New EMI", "Cash remainder"],
                           values=[max(debt, 0), max(emi, 0), available], hole=.73,
                           marker=dict(colors=["#D496AB", "#F0BE72", "#A9E9A9"]),
                           textinfo="none", hovertemplate="%{label}: PKR %{value:,.0f}<extra></extra>"))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="DM Sans, Arial", color="#AEC0D2", size=13),
                      height=310, margin=dict(l=0,r=0,t=12,b=5),
                      showlegend=True, legend=dict(orientation="h", y=-.07, x=.5, xanchor="center"),
                      annotations=[dict(text=f'<b>{m["dti"]:.1f}%</b><br><span style="font-size:12px">projected DTI</span>',
                                        x=.5,y=.5,showarrow=False,font=dict(size=22,color="#EFF8FC"))])
    return fig


def rule_cards(rules: list[dict]) -> None:
    for r in rules:
        st.markdown(
            f'<div class="lw-rule"><span class="code">{esc(r["id"])}</span>'
            f'<div class="desc">{esc(r["explanation"])}</div>'
            f'<div class="meta">{esc(r["category"])} · {esc(r["severity"])}</div></div>',
            unsafe_allow_html=True,
        )


def show_recommendations(result: dict) -> None:
    tips = [r for r in result["rules"] if r["category"] == "improvement"]
    if not tips:
        st.success("No improvement actions are currently triggered by this knowledge base.")
    for r in tips:
        st.markdown(f'<div class="lw-tip"><strong>{esc(r["id"])} ·</strong> {esc(r["explanation"])}</div>',
                    unsafe_allow_html=True)


def init_state() -> None:
    for key, value in sample_case().items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("assessed_case", None)
    st.session_state.setdefault("whatif", None)


init_state()
catalog = rule_catalog()

with st.sidebar:
    st.markdown(
        '<div class="lw-sidebarlogo"><div class="lw-logoicon">LW</div><div class="lw-logotype">Loan<span>Wise</span></div></div>'
        '<div class="lw-sidetag">Expert Decision Intelligence</div>'
        '<div class="lw-sideblock"><div class="lw-overline">SYNTHETIC DEMO PROFILES</div>'
        '<div class="lw-sidecopy">Load a complete example with one click, then run an assessment.</div></div>',
        unsafe_allow_html=True,
    )
    for key, title, tooltip in [
        ("strong", "✦  Strong profile", "High-credit, low-DTI applicant"),
        ("borderline", "◈  Borderline profile", "Documentation and credit review"),
        ("high_risk", "◇  High-risk profile", "Recent default and repayment pressure"),
    ]:
        if st.button(title, use_container_width=True, help=tooltip, key=f"profile_{key}"):
            st.session_state.update(sample_case(key))
            st.session_state["result"] = None
            st.session_state["assessed_case"] = None
            st.session_state["whatif"] = None
            st.rerun()
    engine_ok = engine_available()
    if engine_ok:
        status = '<div class="lw-sidenote"><strong>● SWI-Prolog connected</strong><br>Inference engine available · strict rule-based evaluation</div>'
    else:
        status = '<div class="lw-sidenote"><strong>◌ Prolog runtime missing</strong><br>Install SWI-Prolog to enable actual assessments.</div>'
    st.markdown(
        f'<div class="lw-sideblock lw-sidestatus">{status}'
        f'<div class="lw-sidenote"><strong>{len(catalog)} expert rules</strong><br>'
        '3 lending products · 7 priority decision gates · Explainable proof trace</div>'
        '<div class="lw-sideversion"></div></div>',
        unsafe_allow_html=True,
    )

st.markdown(
    f'<div class="lw-hero"><div class="lw-kicker"><span class="lw-live"></span> KNOWLEDGE-BASED INTELLIGENCE PLATFORM</div>'
    '<div class="lw-hero-title">Better decisions.<br><span>Clearer reasoning.</span></div>'
    '<p class="lw-hero-p">Meet the bank loan expert system that reasons through financial evidence, '
    'applies transparent Prolog policies, and explains every recommendation—before a decision is made.</p>'
    f'<div class="lw-pillrow"><span class="lw-pill">◆ {len(catalog)} Prolog inference rules</span>'
    '<span class="lw-pill">◈ Real-time risk assessment</span>'
    '<span class="lw-pill">✧ What-if simulation</span>'
    '<span class="lw-pill">✓ Fully explainable decisions</span></div></div>',
    unsafe_allow_html=True,
)

if not engine_ok:
    st.warning("SWI-Prolog is not on PATH. The visual interface is available, but decisions are disabled until the genuine Prolog runtime is installed. See README.md.")

application, intelligence, simulation, explorer, methodology = st.tabs([
    "01  ·  Applicant studio", "02  ·  Decision intelligence", "03  ·  What-if lab",
    "04  ·  Rule explorer", "05  ·  Methodology",
])

with application:
    section("Build an applicant profile", "Enter synthetic financial data or select a demo profile in the sidebar.", "APPLICATION WORKSPACE")
    with st.form("application_form", clear_on_submit=False, border=True):
        st.markdown("#### Personal and employment details")
        col1, col2, col3 = st.columns(3, gap="large")
        with col1:
            st.number_input("Applicant age (years)", min_value=18, max_value=90, step=1, key="age")
        with col2:
            st.selectbox("Employment status", options=["salaried", "self_employed", "contract", "unemployed"],
                         format_func=lambda x: {"salaried":"Salaried", "self_employed":"Self-employed", "contract":"Contract", "unemployed":"Unemployed"}[x], key="employment")
        with col3:
            st.number_input("Employment tenure (years)", min_value=0.0,max_value=60.0,step=.5,key="years_employed")
        st.markdown("#### Financial and credit profile")
        a,b,c = st.columns(3,gap="large")
        with a:
            st.number_input("Monthly income (PKR)",min_value=0.0,max_value=10_000_000.0,step=5_000.0,format="%.0f",key="income")
            st.number_input("Savings (PKR)",min_value=0.0,max_value=100_000_000.0,step=10_000.0,format="%.0f",key="savings")
        with b:
            st.number_input("Existing monthly repayments (PKR)",min_value=0.0,max_value=10_000_000.0,step=2_500.0,format="%.0f",key="debt")
            st.number_input("Late payments (past 12 months)",min_value=0,max_value=12,step=1,key="late_payments")
        with c:
            st.number_input("Illustrative credit score (300–850)",min_value=300,max_value=850,step=5,key="credit_score")
            st.checkbox("Default recorded in past 24 months",key="recent_default")
        st.markdown("#### Loan request and verification")
        d,e,f = st.columns(3,gap="large")
        with d:
            st.selectbox("Loan product",options=["personal", "car", "home"],
                         format_func=lambda x:{"personal":"Personal loan", "car":"Car loan", "home":"Home loan"}[x],key="loan_type")
            st.number_input("Requested loan amount (PKR)",min_value=1.0,max_value=50_000_000.0,step=50_000.0,format="%.0f",key="amount")
        with e:
            st.number_input("Loan tenure (months)",min_value=6,max_value=360,step=12,key="term",
                            help="Personal 12–60, Car 12–84, Home 60–300 months. Outside-policy terms are rejected by Prolog.")
            st.number_input("Collateral/asset value (PKR)",min_value=0.0,max_value=100_000_000.0,step=50_000.0,format="%.0f",key="collateral",
                            help="Required for secured car and home loan assessment; enter the underlying asset value.")
        with f:
            st.checkbox("Government ID available",key="has_id")
            st.checkbox("Income proof available",key="income_proof")
            st.checkbox("Bank statements available",key="bank_statements")
        st.caption("All inputs are synthetic. Loan policies, rates, and credit scores are illustrative; no bank data or real applicant identity is used.")
        submitted = st.form_submit_button("✦  Run expert assessment", type="primary", use_container_width=True, disabled=not engine_ok)
    if submitted:
        try:
            app_case = {key:st.session_state[key] for key in sample_case()}
            st.session_state["result"] = assess(app_case)
            st.session_state["assessed_case"] = app_case
            st.session_state["whatif"] = None
            st.success("Expert inference completed. Open **02 · Decision intelligence** for the full analysis and proof trace.")
        except ExpertSystemError as error:
            st.error(str(error))
    if st.session_state["result"]:
        st.markdown("#### Latest assessment")
        decision_banner(st.session_state["result"])
        m = st.session_state["result"]["metrics"]
        kpi_row([("Risk score", f'{st.session_state["result"]["risk_score"]}/100', "Expert-weighted score"),
                 ("Estimated installment", money_short(m["emi"]), "Monthly payment"),
                 ("Projected DTI", f'{m["dti"]:.1f}%', "Including new repayment"),
                 ("Rules fired", str(len(st.session_state["result"]["rules"])), "Evidence from SWI-Prolog")])

with intelligence:
    result = st.session_state["result"]
    case = st.session_state["assessed_case"]
    section("Decision intelligence", "Complete decision support, risk diagnosis, and transparent final inference.", "EXPERT ANALYSIS")
    if result is None:
        empty("No assessment yet", "Run an expert assessment in the Applicant studio, or load a demo profile and evaluate it.")
    else:
        decision_banner(result)
        m = result["metrics"]
        kpi_row([("Expert risk score", f'{result["risk_score"]}/100', f'{result["risk_band"].title()} risk'),
                 ("Monthly installment", money_short(m["emi"]), f'Illustrative {m["interest_rate"]:.1f}% annual rate'),
                 ("Projected DTI", f'{m["dti"]:.1f}%', "Existing debt + new EMI"),
                 ("Monthly surplus", money_short(m["surplus"]), "Remaining after repayments")])
        left, right = st.columns([1.12,.88], gap="large")
        with left:
            st.markdown("#### Financial strength by dimension")
            st.caption("All six factor scores are calculated by the Prolog knowledge base, not predicted by machine learning.")
            st.plotly_chart(score_chart(result["components"]), use_container_width=True, config={"displayModeBar":False})
        with right:
            st.markdown("#### Income allocation")
            st.caption("Modelled affordability assuming fixed monthly installments and the declared income.")
            st.plotly_chart(affordability_chart(case,result),use_container_width=True,config={"displayModeBar":False})
        x,y = st.columns([1,1],gap="large")
        with x:
            st.markdown("#### Decision support · next steps")
            show_recommendations(result)
        with y:
            st.markdown("#### Decision making · proof chain")
            st.markdown(f'<div class="lw-card"><div class="lw-overline">PRIORITY RULE FIRED</div>'
                        f'<h4>{esc(result["decision_rule"])} — {esc(decision_name(result["decision"]))}</h4>'
                        f'<p>{esc(result["decision_reason"])}</p></div>',unsafe_allow_html=True)
            priority = [r for r in result["rules"] if r["severity"] in ("critical", "warning") and r["category"]!="improvement"]
            rule_cards(priority[:8])
            if not priority:
                st.caption("No blocking or cautionary expert evidence was triggered.")
        st.divider()
        section("Inference evidence log", "A complete list of rules that fired for this exact application.", "EXPLAINABILITY")
        selected = st.selectbox("Filter expert evidence",["All", "Critical", "Warning", "Positive", "Info"],key="proof_filter")
        filtered = [r for r in result["rules"] if selected=="All" or r["severity"]==selected.lower()]
        st.dataframe(pd.DataFrame([{"Rule":r["id"],"Module":r["category"].replace("_"," ").title(),
                                   "Level":r["severity"].title(),"Why it fired":r["explanation"]} for r in filtered]),
                     hide_index=True,use_container_width=True)
        st.caption(f'{len(result["rules"])} of {len(catalog)} expert rules fired. Decision rule {result["decision_rule"]} was selected by deterministic priority order.')
        st.download_button("↓ Download evidence report (JSON)",
                           data=json.dumps({"case":case,"assessment":result,"notice":"Synthetic educational assessment only"},indent=2),
                           file_name="loanwise_expert_assessment.json",mime="application/json")
        st.divider()
        section("Loan product comparison", "Same applicant facts, amount, and tenure; each product is re-evaluated by Prolog.", "DECISION SUPPORT")
        rows=[]
        for loan_type in ["personal","car","home"]:
            try:
                variant = assess({**case,"loan_type":loan_type})
                rows.append({"Loan product":loan_type.title(),"Annual rate (demo)":f'{variant["metrics"]["interest_rate"]:.1f}%',
                             "Monthly EMI":money(variant["metrics"]["emi"]),"DTI":f'{variant["metrics"]["dti"]:.1f}%',
                             "Expert decision":decision_name(variant["decision"]),
                             "Priority rule":variant["decision_rule"]})
            except ExpertSystemError as error:
                st.error(f"Could not assess {loan_type}: {error}")
        if rows:
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
            st.caption("Secured products need an asset/collateral value; a personal-loan term may be invalid for a home loan. These are policy consequences, not hidden substitutions.")

with simulation:
    section("What-if scenario lab", "Change the numbers and see how an actual expert-system decision changes.", "DECISION SUPPORT")
    baseline = st.session_state["result"]
    base_case = st.session_state["assessed_case"]
    if baseline is None:
        empty("Explore financial scenarios", "Complete a baseline assessment first. This simulator runs the same Prolog inference rules for every modified scenario.")
    else:
        st.markdown("#### Scenario controls")
        a,b = st.columns(2,gap="large")
        with a:
            inc_change = st.slider("Monthly income change",min_value=-40,max_value=100,value=20,step=5,format="%d%%")
            debt_change = st.slider("Reduce existing monthly debt",min_value=0,max_value=100,value=20,step=5,format="%d%%")
        with b:
            amount_change = st.slider("Requested loan amount change",min_value=-60,max_value=80,value=-10,step=5,format="%d%%")
            term_change = st.slider("Change repayment term (months)",min_value=6,max_value=360,value=base_case["term"],step=6)
        new_case = dict(base_case)
        new_case.update(income=round(base_case["income"]*(1+inc_change/100),2),
                        debt=round(base_case["debt"]*(1-debt_change/100),2),
                        amount=max(1.0,round(base_case["amount"]*(1+amount_change/100),2)),
                        term=term_change)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Scenario income",money_short(new_case["income"]))
        c2.metric("Scenario monthly debt",money_short(new_case["debt"]))
        c3.metric("Scenario loan amount",money_short(new_case["amount"]))
        c4.metric("Scenario tenure",f'{new_case["term"]} months')
        if st.button("◈  Evaluate scenario with Prolog",type="primary",use_container_width=True,disabled=not engine_ok):
            try:
                st.session_state["whatif"]={"case":new_case,"result":assess(new_case)}
            except ExpertSystemError as error:
                st.error(str(error))
        scenario=st.session_state["whatif"]
        if scenario:
            alternative=scenario["result"]
            section("Scenario outcome", "A fresh Prolog proof, never a shortcut heuristic.", "BEFORE / AFTER")
            left,right = st.columns(2,gap="large")
            with left:
                st.markdown("**Baseline assessment**")
                decision_banner(baseline)
                st.metric("Expert risk score",f'{baseline["risk_score"]}/100')
                st.metric("Projected DTI",f'{baseline["metrics"]["dti"]:.1f}%')
            with right:
                st.markdown("**Modified scenario**")
                decision_banner(alternative)
                st.metric("Expert risk score",f'{alternative["risk_score"]}/100',
                          delta=f'{alternative["risk_score"]-baseline["risk_score"]:+d} points')
                st.metric("Projected DTI",f'{alternative["metrics"]["dti"]:.1f}%',
                          delta=f'{alternative["metrics"]["dti"]-baseline["metrics"]["dti"]:+.1f} pp',delta_color="inverse")
            st.markdown("#### New scenario decision justification")
            rule_cards([r for r in alternative["rules"] if r["category"]=="decision"])
            with st.expander(f"Inspect all {len(alternative['rules'])} triggered scenario rules"):
                rule_cards(alternative["rules"])

with explorer:
    section("Inside the knowledge base", "Explore the actual condition-bearing Prolog clauses, grouped by expert module.", "KNOWLEDGE ENGINEERING")
    groups = Counter(r["category"] for r in catalog)
    kpi_row([("Real inference rules",str(len(catalog)),"Counted from the .pl source"),
             ("Knowledge domains",str(len(groups)),"Including decision policy"),
             ("Decision priorities",str(groups["decision"]),"Deterministic first match"),
             ("Loan policies","3 products","Personal · Car · Home")])
    cat_names=["All modules"]+sorted(groups)
    category = st.selectbox("Knowledge module",cat_names)
    only_fired = st.checkbox("Only rules that fired for the last assessment",key="only_fired")
    search = st.text_input("Search rule IDs or explanations",placeholder="Try credit, DTI, collateral, D05...")
    fired={r["id"] for r in st.session_state["result"]["rules"]} if st.session_state["result"] else set()
    shown=[r for r in catalog if (category=="All modules" or r["category"]==category)
           and (not only_fired or r["id"] in fired)
           and (not search or search.lower() in (r["id"]+" "+r["explanation"]).lower())]
    st.caption(f"Showing {len(shown)} of {len(catalog)} live knowledge-base rules.")
    left,right=st.columns(2,gap="large")
    for i,r in enumerate(shown):
        with (left if i%2==0 else right):
            rule_cards([r])

with methodology:
    section("A real expert system, not a black box", "Knowledge acquisition, inference, decision support and explanation—separately and transparently.", "PROJECT METHODOLOGY")
    st.markdown("""
#### How LoanWise reasons

1. **Fact acquisition:** The form captures a validated synthetic applicant profile, financial obligations and product request.
2. **Knowledge representation:** SWI-Prolog stores fictional lending policies, 68 conditional rules and seven prioritized decision clauses.
3. **Inference:** Prolog computes amortization, DTI, loan-to-value and evidence-based scores, then selects the first matching decision gate.
4. **Explanation:** The engine returns every fired rule (ID, module, severity and reason), including the decision proof.
5. **Decision Support System:** Compares loan products, explains affordability and generates actionable, conditional improvements and what-if analyses.
6. **Decision Making System:** Returns exactly one of **Approved**, **Manual review**, or **Rejected**, based entirely on Prolog.
""")
    x,y=st.columns(2,gap="large")
    with x:
        st.markdown('<div class="lw-card"><div class="lw-overline">EXPERT KNOWLEDGE</div><h4>Inference logic</h4><p>Each rule encodes a meaningful domain condition. Rule hits and final decisions are not fabricated frontend labels.</p></div>',unsafe_allow_html=True)
        st.markdown('<div class="lw-card"><div class="lw-overline">PRIORITY ORDER</div><h4>Deterministic decisions</h4><p>D01 age → D02 credit defaults → D03 severe DTI → D04 product validity → D05 compliance review → D06 risk review → D07 approve.</p></div>',unsafe_allow_html=True)
    with y:
        st.markdown('<div class="lw-card"><div class="lw-overline">RISK MODEL</div><h4>Transparent weightings</h4><p>Credit 25%, affordability 30%, employment 15%, payment history 15%, collateral/security 10%, documents 5%.</p></div>',unsafe_allow_html=True)
        st.markdown('<div class="lw-card"><div class="lw-overline">ACADEMIC ETHICS</div><h4>Fictional, privacy-first</h4><p>No real customer identities, banking integrations, or server-side applicant database. Inputs remain in the active Streamlit session.</p></div>',unsafe_allow_html=True)
    st.info("**Important:** All interest rates, lending criteria and risk thresholds are educational assumptions. These results are not lending advice, credit underwriting, regulatory compliance findings or a real bank decision. Do not use real applicant data.")

st.markdown('<div class="lw-foot">© 2026 LoanWise</div>',unsafe_allow_html=True)
