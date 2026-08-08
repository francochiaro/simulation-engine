# Law's 17 pitfalls — pre-flight checklist

Skim before writing `model.py`; re-check before delivering `report.md`.
(THEORY §2.3 for the annotated version.)

**Modeling & validation**
- [ ] Objectives well-defined at the start (specific questions, not themes)
- [ ] The user understands what simulation gives (samples + CIs, not oracles)
- [ ] Regular check-ins — the walk-through happened, iterations shown
- [ ] Input data quality assessed honestly (data vs guesses, per source)
- [ ] Level of detail matched to objectives — no one-to-one system copying
- [ ] The study is mostly modeling & analysis, not code
- [ ] Statistics done by the book (Parts 4–5), not vibes

**Software**
- [ ] Conversational interface ≠ less rigor (the whole point of this list)
- [ ] Engine assumptions understood (block semantics — SKILL.md gotchas)
- [ ] Animation used for validation & communication, never as evidence

**Randomness**
- [ ] No distribution replaced by its mean, anywhere
- [ ] No normal/uniform where a duration belongs
- [ ] Triangular only under data poverty, flagged in the A-register

**Design & analysis**
- [ ] Output statistics reported as estimates with CIs
- [ ] Warm-up applied for steady-state questions (Welch evidence kept)
- [ ] No classical stats on within-run (autocorrelated) data — replications
      are the unit of analysis
