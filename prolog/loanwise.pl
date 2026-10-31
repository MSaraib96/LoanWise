/**
 * LoanWise expert system — fictional academic lending policies.
 * SWI-Prolog knowledge base: 68 distinct, condition-bearing inference rules.
 * No rules or decisions are inferred by Streamlit/Python.
 * Protocol: one JSON applicant object on stdin; one JSON analysis on stdout.
 */
:- use_module(library(http/json)).
:- use_module(library(lists)).
:- use_module(library(apply)).

v(D, K, V) :- get_dict(K, D, V).

% Annual percentage rates and limits are fictitious demo assumptions, not bank offers.
policy(personal, 17.0, 12, 60, 2000000, 45000, 0).
policy(car, 12.5, 12, 84, 8000000, 70000, 85).
policy(home, 10.5, 60, 300, 30000000, 110000, 80).

policy_for(C, Rate, MinTerm, MaxTerm, MaxAmount, MinIncome, MaxLtv) :-
    v(C, loan_type, Loan), policy(Loan, Rate, MinTerm, MaxTerm, MaxAmount, MinIncome, MaxLtv).

metrics(C, M) :-
    v(C, income, Income), v(C, debt, Debt), v(C, amount, Amount),
    v(C, term, Term), v(C, collateral, Collateral),
    policy_for(C, AnnualRate, _, _, _, _, _),
    MonthlyRate is AnnualRate / 1200,
    Growth is (1 + MonthlyRate) ** Term,
    EMI is Amount * MonthlyRate * Growth / (Growth - 1),
    ( Income > 0 -> DTI is (Debt + EMI) * 100 / Income,
      ExistingDTI is Debt * 100 / Income,
      StressDTI is (Debt + EMI) * 100 / (Income * 0.85),
      EmiPct is EMI * 100 / Income
    ; DTI = 999, ExistingDTI = 999, StressDTI = 999, EmiPct = 999 ),
    ( Collateral > 0 -> LTV is Amount * 100 / Collateral ; LTV = 999 ),
    Surplus is Income - Debt - EMI,
    M = _{emi:EMI, dti:DTI, existing_dti:ExistingDTI, stress_dti:StressDTI,
          emi_pct:EmiPct, ltv:LTV, surplus:Surplus, interest_rate:AnnualRate}.

% Expert scores: derived entirely from financial evidence within Prolog.
credit_component(C, S) :- v(C, credit_score, X),
    ( X >= 800 -> S=100 ; X >= 750 -> S=93 ; X >= 700 -> S=84 ;
      X >= 660 -> S=73 ; X >= 600 -> S=57 ; X >= 520 -> S=30 ; S=5 ).
affordability_component(M, S) :- v(M, dti, X),
    ( X =< 25 -> S=100 ; X =< 35 -> S=88 ; X =< 40 -> S=75 ;
      X =< 45 -> S=60 ; X =< 55 -> S=35 ; S=5 ).
employment_component(C, S) :- v(C, employment, E), v(C, years_employed, Y),
    ( E == salaried, Y >= 3 -> S=100
    ; E == salaried, Y >= 1 -> S=85
    ; E == self_employed, Y >= 3 -> S=85
    ; E == self_employed, Y >= 1 -> S=65
    ; E == contract, Y >= 2 -> S=60
    ; E == unemployed -> S=0
    ; S=35 ).
history_component(C, S) :- v(C, recent_default, Default), v(C, late_payments, Late),
    ( Default == true -> S=0 ; Late >= 3 -> S=35 ; Late >= 1 -> S=70 ; S=100 ).
security_component(C, M, S) :- v(C, loan_type, Loan), v(M, ltv, LTV),
    ( Loan == personal -> S=80
    ; LTV =< 60 -> S=100 ; LTV =< 80 -> S=90 ; LTV =< 85 -> S=75
    ; LTV =< 100 -> S=40 ; S=0 ).
document_component(C, S) :- v(C, has_id, I), v(C, income_proof, P), v(C, bank_statements, B),
    ( I == true, P == true, B == true -> S=100
    ; I == true, P == true -> S=65
    ; I == true -> S=40 ; S=0 ).

component_scores(C, M, D) :-
    credit_component(C, Credit), affordability_component(M, Afford),
    employment_component(C, Employment), history_component(C, History),
    security_component(C, M, Security), document_component(C, Docs),
    D = _{credit:Credit, affordability:Afford, employment:Employment,
          history:History, security:Security, documents:Docs}.

risk_score(C, M, Score) :- component_scores(C, M, D),
    Weighted is D.credit * 0.25 + D.affordability * 0.30 +
                D.employment * 0.15 + D.history * 0.15 +
                D.security * 0.10 + D.documents * 0.05,
    Score is round(Weighted).
risk_band(S, low) :- S >= 80, !.
risk_band(S, moderate) :- S >= 60, !.
risk_band(_, high).

has_all_documents(C) :- v(C,has_id,true), v(C,income_proof,true), v(C,bank_statements,true).

% Seven ordered, mutually exclusive decision inference clauses. First match wins.
% D01: Hard policy block — age.
decision(C, _, rejected, 'D01', 'Outside the permitted simulated age range (21–65).') :-
    v(C,age,Age), (Age < 21 ; Age > 65), !.
% D02: Hard block — severe credit evidence.
decision(C, _, rejected, 'D02', 'Recent default or critical credit score below 520.') :-
    v(C,recent_default,Default), v(C,credit_score,Credit),
    (Default == true ; Credit < 520), !.
% D03: Hard block — inability to service debt.
decision(_, M, rejected, 'D03', 'Post-loan debt-to-income exceeds 55%, or monthly surplus is negative.') :-
    v(M,dti,Dti), v(M,surplus,Surplus), (Dti > 55 ; Surplus < 0), !.
% D04: Hard block — unsupported product, term, amount, or employment.
decision(C, M, rejected, 'D04', 'Outside absolute loan/product policy limits or no verifiable employment.') :-
    policy_for(C,_,MinT,MaxT,MaxA,_,_), v(C,term,Term), v(C,amount,Amount),
    v(C,employment,E), v(C,loan_type,Loan), v(M,ltv,Ltv),
    (Term < MinT ; Term > MaxT ; Amount > MaxA ; Amount =< 0 ; E == unemployed ;
      (Loan \== personal, Ltv > 100)), !.
% D05: Review for incomplete documentation, weaker credit, or collateral/income gaps.
decision(C, M, manual_review, 'D05', 'A required document, product minimum, credit policy, or security margin needs review.') :-
    policy_for(C,_,_,_,_,MinIncome,MaxLTV), v(C,income,Income),
    v(C,credit_score,Credit), v(C,loan_type,Loan), v(M,ltv,LTV),
    ( \+ has_all_documents(C) ; Income < MinIncome ; Credit < 660 ;
      (Loan \== personal, LTV > MaxLTV)), !.
% D06: Review for risk and repayment pressures.
decision(C, M, manual_review, 'D06', 'Risk, repayment burden, or limited employment tenure requires human review.') :-
    risk_score(C,M,Score), v(M,dti,Dti), v(M,stress_dti,Stress),
    v(C,years_employed,Years), v(C,employment,E),
    v(C,late_payments,Late), v(C,age,Age), v(C,term,Term),
    ( Score < 72 ; Dti > 40 ; Stress > 50 ; Years < 1 ;
      Late >= 3 ; Age + Term/12 > 65 ;
      (E == contract, Years < 2)), !.
% D07: All simulated policy gates passed.
decision(_, _, approved, 'D07', 'All mandatory policy gates passed at the supplied financial inputs.').

% ── Basic eligibility: B01–B08 (8 rules) ───────────────────────────────────
rule(C,_,'B01',basic,critical,'Applicant is below the minimum age of 21.') :- v(C,age,A), A < 21.
rule(C,_,'B02',basic,critical,'Applicant is above the maximum age of 65.') :- v(C,age,A), A > 65.
rule(C,_,'B03',basic,positive,'Applicant meets the simulated age requirement.') :- v(C,age,A), between(21,65,A).
rule(C,_,'B04',basic,warning,'Government ID verification is missing.') :- v(C,has_id,false).
rule(C,_,'B05',basic,warning,'Income verification documentation is missing.') :- v(C,income_proof,false).
rule(C,_,'B06',basic,warning,'Bank statements are missing.') :- v(C,bank_statements,false).
rule(C,_,'B07',basic,positive,'All required application documents are provided.') :- has_all_documents(C).
rule(C,_,'B08',basic,warning,'Applicant will be 60 or older at loan maturity.') :- v(C,age,A),v(C,term,T),A+T/12 >= 60.

% ── Employment stability: E01–E08 (8 rules) ────────────────────────────────
rule(C,_,'E01',employment,positive,'Salaried employment has at least three years of tenure.') :- v(C,employment,salaried),v(C,years_employed,Y),Y>=3.
rule(C,_,'E02',employment,positive,'Salaried applicant has one to three years of tenure.') :- v(C,employment,salaried),v(C,years_employed,Y),Y>=1,Y<3.
rule(C,_,'E03',employment,warning,'Salaried employment tenure is under one year.') :- v(C,employment,salaried),v(C,years_employed,Y),Y<1.
rule(C,_,'E04',employment,positive,'Self-employed applicant has three or more years of operating history.') :- v(C,employment,self_employed),v(C,years_employed,Y),Y>=3.
rule(C,_,'E05',employment,warning,'Self-employment history is shorter than three years.') :- v(C,employment,self_employed),v(C,years_employed,Y),Y<3.
rule(C,_,'E06',employment,positive,'Contract role is backed by two or more years of experience.') :- v(C,employment,contract),v(C,years_employed,Y),Y>=2.
rule(C,_,'E07',employment,warning,'Contract employment history is below two years.') :- v(C,employment,contract),v(C,years_employed,Y),Y<2.
rule(C,_,'E08',employment,critical,'Applicant has no current employment under model assumptions.') :- v(C,employment,unemployed).

% ── Credit history: C01–C10 (10 rules) ────────────────────────────────────
rule(C,_,'C01',credit,positive,'Exceptional simulated credit score: 800–850.') :- v(C,credit_score,X),X>=800.
rule(C,_,'C02',credit,positive,'Excellent simulated credit score: 750–799.') :- v(C,credit_score,X),X>=750,X<800.
rule(C,_,'C03',credit,positive,'Good simulated credit score: 700–749.') :- v(C,credit_score,X),X>=700,X<750.
rule(C,_,'C04',credit,info,'Satisfactory simulated credit score: 660–699.') :- v(C,credit_score,X),X>=660,X<700.
rule(C,_,'C05',credit,warning,'Credit score of 600–659 prompts a manual-review gate.') :- v(C,credit_score,X),X>=600,X<660.
rule(C,_,'C06',credit,warning,'Weak credit score of 520–599 prompts a manual-review gate.') :- v(C,credit_score,X),X>=520,X<600.
rule(C,_,'C07',credit,critical,'Credit score below 520 triggers a hard policy block.') :- v(C,credit_score,X),X<520.
rule(C,_,'C08',credit,positive,'No late payments reported during the last 12 months.') :- v(C,late_payments,0).
rule(C,_,'C09',credit,warning,'One or two late payments reported in the last 12 months.') :- v(C,late_payments,N),N>=1,N=<2.
rule(C,_,'C10',credit,critical,'Three or more late payments reported in the last 12 months.') :- v(C,late_payments,N),N>=3.

% ── Affordability: A01–A10 (10 rules) ─────────────────────────────────────
rule(_,M,'A01',affordability,positive,'Projected DTI is at or below 25%.') :- v(M,dti,X),X=<25.
rule(_,M,'A02',affordability,positive,'Projected DTI is above 25% and at or below 35%.') :- v(M,dti,X),X>25,X=<35.
rule(_,M,'A03',affordability,info,'Projected DTI is above 35% and at or below 40%.') :- v(M,dti,X),X>35,X=<40.
rule(_,M,'A04',affordability,warning,'Projected DTI is above 40% and at or below 45%.') :- v(M,dti,X),X>40,X=<45.
rule(_,M,'A05',affordability,warning,'Projected DTI is above 45% and at or below 55%.') :- v(M,dti,X),X>45,X=<55.
rule(_,M,'A06',affordability,critical,'Projected DTI exceeds the 55% hard limit.') :- v(M,dti,X),X>55.
rule(_,M,'A07',affordability,warning,'Monthly post-repayment cash surplus is below PKR 10,000.') :- v(M,surplus,X),X<10000.
rule(_,M,'A08',affordability,positive,'Monthly post-repayment cash surplus exceeds PKR 50,000.') :- v(M,surplus,X),X>=50000.
rule(_,M,'A09',affordability,warning,'Existing debt consumes more than 40% of monthly income.') :- v(M,existing_dti,X),X>40.
rule(_,M,'A10',affordability,warning,'Proposed new installment exceeds 30% of gross monthly income.') :- v(M,emi_pct,X),X>30.

% ── Product policies: L01–L10 (10 rules) ──────────────────────────────────
rule(C,_,'L01',product,positive,'Personal loan amount is within its PKR 2,000,000 cap.') :- v(C,loan_type,personal),v(C,amount,X),X>0,X=<2000000.
rule(C,_,'L02',product,critical,'Personal loan amount exceeds PKR 2,000,000.') :- v(C,loan_type,personal),v(C,amount,X),X>2000000.
rule(C,_,'L03',product,positive,'Car loan amount is within its PKR 8,000,000 cap.') :- v(C,loan_type,car),v(C,amount,X),X>0,X=<8000000.
rule(C,M,'L04',product,warning,'Car loan LTV exceeds the 85% model policy threshold.') :- v(C,loan_type,car),v(M,ltv,X), X>85.
rule(C,_,'L05',product,positive,'Home loan amount is within its PKR 30,000,000 cap.') :- v(C,loan_type,home),v(C,amount,X),X>0,X=<30000000.
rule(C,M,'L06',product,warning,'Home loan LTV exceeds the 80% model policy threshold.') :- v(C,loan_type,home),v(M,ltv,X),X>80.
rule(C,_,'L07',product,critical,'Requested term falls outside the loan product range.') :- policy_for(C,_,Min,Max,_,_,_),v(C,term,T),(T<Min;T>Max).
rule(C,_,'L08',product,critical,'Requested loan amount must be greater than zero.') :- v(C,amount,X),X=<0.
rule(C,_,'L09',product,critical,'Loan amount exceeds car/home product maximum.') :- v(C,loan_type,T),T\==personal, policy_for(C,_,_,_,Max,_,_),v(C,amount,A),A>Max.
rule(C,_,'L10',product,warning,'Declared income is below the product-specific minimum.') :- policy_for(C,_,_,_,_,Min,_),v(C,income,I),I<Min.

% ── Risk diagnostics: R01–R08 (8 rules) ───────────────────────────────────
rule(C,M,'R01',risk,positive,'Composite expert score is at least 85/100.') :- risk_score(C,M,S),S>=85.
rule(C,M,'R02',risk,info,'Composite expert score is in the 70–84 range.') :- risk_score(C,M,S),S>=70,S<85.
rule(C,M,'R03',risk,warning,'Composite expert score is in the 55–69 range.') :- risk_score(C,M,S),S>=55,S<70.
rule(C,M,'R04',risk,critical,'Composite expert score is below 55/100.') :- risk_score(C,M,S),S<55.
rule(C,M,'R05',risk,critical,'Recent default indicates elevated historical repayment risk.') :- v(C,recent_default,true).
rule(C,M,'R06',risk,warning,'DTI exceeds 45% and late payments were reported.') :- v(M,dti,D),D>45,v(C,late_payments,N),N>0.
rule(C,M,'R07',risk,warning,'Savings buffer covers fewer than three projected installments.') :- v(C,savings,S),v(M,emi,EMI),S<3*EMI.
rule(C,M,'R08',risk,positive,'Savings buffer covers at least six projected installments.') :- v(C,savings,S),v(M,emi,EMI),S>=6*EMI.

% ── Decision rules D01–D07 are implemented above; these expose fired proof. ─
rule(C,M,ID,decision,Severity,Reason) :- decision(C,M,Outcome,ID,Reason),
    ( Outcome == rejected -> Severity = critical
    ; Outcome == manual_review -> Severity = warning ; Severity = positive ).

% ── Guidance rules I01–I07 (7 rules) ──────────────────────────────────────
rule(_,M,'I01',improvement,info,'Reducing existing monthly debts may improve projected DTI.') :- v(M,existing_dti,X),X>20.
rule(_,M,'I02',improvement,info,'A smaller requested amount may improve monthly affordability.') :- v(M,dti,X),X>35.
rule(C,M,'I03',improvement,info,'A longer permitted term can lower EMI, but increases total interest.') :- policy_for(C,_,_,Max,_,_,_),v(C,term,T),T<Max,v(M,dti,D),D>35.
rule(C,_,'I04',improvement,info,'Improving repayment behavior and credit standing may help eligibility.') :- v(C,credit_score,X),X<700.
rule(C,_,'I05',improvement,info,'Provide all ID, income, and bank-statement documents.') :- \+ has_all_documents(C).
rule(C,M,'I06',improvement,info,'Increasing the down payment can reduce secured-loan LTV.') :- v(C,loan_type,T),T\==personal,policy_for(C,_,_,_,_,_,MaxLTV),v(M,ltv,L),L>MaxLTV.
rule(C,M,'I07',improvement,info,'Building an emergency buffer of six installments may improve resilience.') :- v(C,savings,S),v(M,emi,E),S<6*E.

% Create deterministic ordered outputs with the unique rule IDs that fired.
triggered(C,M,Rules) :-
    findall(_{id:ID,category:Category,severity:Severity,explanation:Text},
            rule(C,M,ID,Category,Severity,Text), Rules).

evaluate(C, Output) :-
    metrics(C,M), component_scores(C,M,Components), risk_score(C,M,Score),
    risk_band(Score,Band), decision(C,M,Decision,DecisionID,Reason),
    triggered(C,M,Rules),
    policy_for(C,_,MinTerm,MaxTerm,MaxAmount,MinIncome,MaxLTV),
    Output = _{decision:Decision, decision_rule:DecisionID, decision_reason:Reason,
               risk_score:Score, risk_band:Band, metrics:M, components:Components,
               rules:Rules, policies:_{min_term:MinTerm,max_term:MaxTerm,
               max_amount:MaxAmount,min_income:MinIncome,max_ltv:MaxLTV}}.

main :- catch((json_read_dict(current_input,Data),
                get_dict(employment,Data,EmpString),atom_string(Emp,EmpString),
                get_dict(loan_type,Data,LoanString),atom_string(Loan,LoanString),
                put_dict(_{employment:Emp,loan_type:Loan},Data,Case),
                evaluate(Case,Result),json_write_dict(current_output,Result),nl),
             Error,(message_to_string(Error,Msg),
                    json_write_dict(current_output,_{error:Msg}),nl,halt(2))).
