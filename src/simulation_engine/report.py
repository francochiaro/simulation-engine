"""Markdown report generator — the quantitative skeleton of the study report.

``build_report`` turns run artifacts into the report.md structure the
/simulate skill promises: question, conceptual-model reference, validation
evidence, results with CIs (never a bare point estimate), scenario verdicts,
and the assumptions/simplifications registers. The agent (or author) then
appends narrative; this module owns every number so none get retyped wrong.

Sections are emitted only when their inputs are provided.
"""

from __future__ import annotations

import math
import os


def _fmt(x, digits: int = 3) -> str:
    """NaN/None-safe number formatting — never prints the literal 'nan'."""
    if x is None:
        return "–"
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return "–"
    if isinstance(x, float):
        if x != 0 and abs(x) < 10 ** -digits:
            return f"{x:.2e}"
        s = f"{x:,.{digits}f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-") else "0"
    return f"{x:,}"


def _scenario_label(scenario: dict) -> str:
    return ", ".join(f"{k}={_fmt(v) if isinstance(v, (int, float)) else v}"
                     for k, v in sorted(scenario.items()))


def build_report(
    *,
    question: str,
    title: str | None = None,
    run_result=None,
    replications=None,
    theory: dict | None = None,
    sweep_result=None,
    sweep_kpi: str | None = None,
    baseline: int = 0,
    conceptual_model: str | None = None,
    assumptions: list[str] | None = None,
    simplifications: list[str] | None = None,
    next_steps: list[str] | None = None,
    kpi_prefixes: tuple[str, ...] | None = None,
    out_path: str | None = None,
) -> str:
    """Assemble report.md. All inputs optional except ``question``.

    - ``run_result``: a showcase ``RunResult`` — supplies entity-balance and
      Little's-Law evidence.
    - ``replications``: a ``ReplicationsResult`` — KPI tables (mean ± CI and
      P10/P50/P90 across replications).
    - ``theory``: the dict from ``theory_check.check()``.
    - ``sweep_result`` + ``sweep_kpi``: scenario table and Δ-vs-baseline
      verdicts ("distinguishable" / "cannot distinguish").
    - ``conceptual_model``: markdown text, referenced (headline only) rather
      than inlined — conceptual-model.md stands on its own.
    - ``kpi_prefixes``: keep only KPIs starting with one of these prefixes
      in the results tables (default: all).
    - ``out_path``: also write the markdown there when given.
    """
    L: list[str] = []
    L.append(f"# {title or 'Simulation study report'}")
    L.append("")
    L.append("## Question")
    L.append("")
    L.append(question.strip())

    if conceptual_model:
        first = next(
            (ln.lstrip("# ").strip() for ln in conceptual_model.splitlines()
             if ln.strip().startswith("#")),
            "conceptual model",
        )
        L += ["", "## Conceptual model", "",
              f"See `conceptual-model.md` — *{first}*. The conceptual model is "
              f"the model; the code is an implementation of it."]

    # ---- validation evidence -------------------------------------------
    evidence: list[str] = []
    if run_result is not None:
        ent = run_result.kpis["entities"]
        mark = "✓" if ent["balance_ok"] else "✗"
        evidence.append(
            f"- {mark} **Entity balance**: created {ent['created']} = disposed "
            f"{ent['disposed']} + dropped {ent['dropped']} + in system at end "
            f"{ent['in_system_at_end']}"
        )
        little = run_result.kpis["little"]
        if little.get("residual_rel") is not None:
            ok = little["residual_rel"] < 0.05
            evidence.append(
                f"- {'✓' if ok else '✗'} **Little's Law**: L = {_fmt(little['L'])} vs "
                f"λ·W = {_fmt(little['lambda'] * little['W'])} "
                f"(residual {_fmt(little['residual_rel'] * 100, 2)}%)"
            )
    if theory:
        mark = "✓" if theory.get("all_covered") else "✗"
        evidence.append(
            f"- {mark} **Analytic reference ({theory['reference']})**: every "
            f"simulated 95% CI must cover its exact value"
            + ("" if theory.get("all_covered") else " — **coverage failure, investigate**")
        )
    if evidence:
        L += ["", "## Validation evidence", ""]
        L += evidence
    if theory:
        L += ["", "| metric | analytic | simulated 95% CI | covered |",
              "|---|---|---|---|"]
        for m in theory["metrics"]:
            L.append(
                f"| {m['metric']} | {_fmt(m['analytic'])} | "
                f"[{_fmt(m['ci_low'])}, {_fmt(m['ci_high'])}] | "
                f"{'✓' if m['covered'] else '✗'} |"
            )
        if theory.get("note"):
            L += ["", f"*{theory['note']}*"]

    # ---- results --------------------------------------------------------
    if replications is not None:
        keep = (lambda k: k.startswith(kpi_prefixes)) if kpi_prefixes else (lambda k: True)
        conf = f"{replications.confidence:.0%}"
        L += ["", f"## Results — {replications.n} replications, {conf} confidence", "",
              f"| KPI | mean | {conf} CI | rel. precision |", "|---|---|---|---|"]
        table = replications.table()
        for k, s in table.items():
            if not keep(k) or s["n"] < 2 or s["mean"] is None:
                continue
            rp = s.get("rel_precision")
            L.append(
                f"| {k} | {_fmt(s['mean'])} | [{_fmt(s['ci_low'])}, {_fmt(s['ci_high'])}] | "
                f"{_fmt(rp * 100, 1) + '%' if rp is not None and not math.isnan(rp) else '–'} |"
            )
        L += ["", "Distribution across replications (the output *is* a distribution — "
              "THEORY.md §8.1):", "",
              "| KPI | P10 | P50 | P90 |", "|---|---|---|---|"]
        for k in table:
            if not keep(k):
                continue
            p = replications.percentiles(k)
            L.append(f"| {k} | {_fmt(p['p10'])} | {_fmt(p['p50'])} | {_fmt(p['p90'])} |")
        seq = replications.sequential
        if seq:
            L += ["", f"*Sequential replication policy on `{seq['kpi']}`: target "
                  f"{_fmt(seq['target_precision'] * 100, 1)}% relative half-width, achieved "
                  f"{_fmt(seq['achieved_precision'] * 100, 1)}% after {seq['n_run']} "
                  f"replications{'' if seq['converged'] else ' (NOT converged)'}.*"]

    # ---- scenarios ------------------------------------------------------
    if sweep_result is not None and sweep_kpi:
        conf = f"{sweep_result.confidence:.0%}"
        L += ["", f"## Scenario comparison — `{sweep_kpi}`", "",
              f"| scenario | mean | {conf} CI |", "|---|---|---|"]
        for row in sweep_result.table(sweep_kpi):
            L.append(
                f"| {_scenario_label(row['scenario'])} | {_fmt(row['mean'])} | "
                f"[{_fmt(row['ci_low'])}, {_fmt(row['ci_high'])}] |"
            )
        base_label = _scenario_label(sweep_result.scenarios[baseline])
        pairing = "paired (CRN)" if sweep_result.crn else "independent"
        L += ["", f"Differences vs baseline ({base_label}), {pairing} CIs:", "",
              "| scenario | Δ vs baseline | CI on Δ | verdict |", "|---|---|---|---|"]
        for row in sweep_result.compare(sweep_kpi, baseline=baseline):
            verdict = ("**distinguishable**" if row["distinguishable"]
                       else "cannot distinguish")
            L.append(
                f"| {_scenario_label(row['scenario'])} | {_fmt(row['diff_mean'])} | "
                f"[{_fmt(row['ci_low'])}, {_fmt(row['ci_high'])}] | {verdict} |"
            )
        L += ["", "*Rankings come from CIs on differences, never from point estimates; "
              "\"the data cannot distinguish these scenarios\" is a valid answer.*"]

    # ---- registers ------------------------------------------------------
    if assumptions:
        L += ["", "## Assumptions register", ""]
        L += [f"- {a}" for a in assumptions]
    if simplifications:
        L += ["", "## Simplifications", ""]
        L += [f"- {s}" for s in simplifications]
    if next_steps:
        L += ["", "## What would sharpen the answer", ""]
        L += [f"- {s}" for s in next_steps]

    md = "\n".join(L) + "\n"
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(md)
    return md
