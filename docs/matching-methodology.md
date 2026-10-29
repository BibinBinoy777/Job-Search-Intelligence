# Matching methodology

Current ranking identity: `evidence-baseline-1.0.1+d5546bafea1c`. Extractor: `requirements-1.0`; skill taxonomy: `skills-1.0`. The configuration manifest is persisted with each assessment. Version 1.0.1 corrects incomplete-profile guidance; weights are unchanged. A method or explanation change requires a base version bump; weights and manifest changes also produce a new configuration fingerprint automatically.

This is a deterministic record-based relevance baseline. A score is neither interview/offer probability nor proof that every qualification is met. It does not learn from this dataset or candidate behavior.

## Components

Every available component is in [0,1]. Unavailable components are null, not zero.

| Component | Weight | Meaning |
|---|---:|---|
| Required skills | 0.40 | Fraction of distinct identified required skills with recorded candidate evidence |
| Preferred skills | 0.10 | Corresponding fraction for preferred skills, kept separate |
| Experience | 0.20 | Relevant documented years / explicit required minimum, capped at 1; without a years requirement, supported responsibility/project technology overlap |
| Role | 0.15 | Maximum Jaccard overlap of recognized role tokens between vacancy title and recorded target/headline/previous titles |
| Location preferences | 0.10 | Mean of comparable work-arrangement and preferred-location checks; separate from hard country restrictions |
| Other preferences | 0.05 | Mean of available employment-type, comparable annual salary-bound and recognized career-level preference checks |

For available components A, score = round(100 × sum(w_i × f_i for i in A) / sum(w_i for i in A), 2). Applicable scoring weight is sum(w_i for i in A). A zero means an assessed component has no recorded overlap; it does not assert the person lacks a capability. Missing candidate skills or unidentified requirements leave skill components null. A missing description, no professional evidence, or no assessable professional component yields a null score and insufficient-information state. Target titles/preferences alone cannot unlock a score; recorded skills, experience or projects are required. A resume is optional.

The mean renormalizes available weights. This has a material limitation: a job with only role/location/preferences can score 100 with just 30% of the scoring weight assessed and no measurable requirement coverage. Such a result was observed in the genuine-job QA run. The UI displays both missing components and weight coverage, but the ordering does not apply a coverage penalty or calibration. Scores with different available components are not directly comparable as complete assessments.

## Evidence and extraction

Recorded skills and experience technologies are explicit evidence. Recognized skill mentions in professional text/projects are derived evidence, with source paths and exact text. Derived mentions are not verified expertise. Negative candidate mentions are excluded. Java and JavaScript remain distinct; ambiguous Go/R/C prose is not broadly inferred. Aliases are small and inspectable.

Job structured skill fields are authoritative. Prose classification uses recognized section headings, required/preferred cues and negation; incidental company/benefit/stack mentions do not become required skills. Repeated aliases are deduplicated and evidence spans retain their individual classification. Alternative skill clauses such as Python or Java are conservatively marked incidental/ambiguous with review warnings rather than invented as jointly mandatory. Arbitrary headings, complex prose, equivalence and unknown technologies can be missed or misclassified. Source categories are not mandatory skills or reliable industries.

Relevant experience requires recorded role or technology context. Overlapping intervals merge; only records with both dates and an end date no later than assessment day contribute years. Undated/ongoing records remain visible but cannot establish completed duration. Projects provide contextual overlap, never invented employment years. Multiple scoped years requirements are conservatively combined; this is a lower-bound heuristic, not a complete career history assessment. Preferred years and formal qualification equivalence do not get independent score components.

Salary compatibility needs a disclosed bound, the same currency and annual pay period. It is an indicator against that bound, not proof of an offer or currency-adjusted purchasing power. Missing/incomparable salary remains unknown. Unknown work arrangement/location is not assumed remote or worldwide. Industry, relocation feasibility, timezone eligibility and detailed career progression are not automatically resolved.

## Eligibility and coverage

Eligibility is separate from the weighted score. Individually named checks distinguish source availability from candidate constraints. Closed/expired records and explicit country mismatch are excluded from normal recommendations. Recent source confirmation is only evidence the vacancy is open, never evidence the candidate meets its requirements. The optional voluntarily supplied current country can be compared to explicit recognized country restrictions; target locations, relocation willingness and identity are not residence evidence. Region labels and unsupported countries stay unknown. Residence is not work authorization. Authorization, clearance, required licence/certification and degree equivalence remain manual-review unknowns. Missing skill evidence is unknown eligibility, not a confirmed inability.

Overall eligibility is confirmed mismatch if a check establishes a mismatch, unknown if any check is unknown, otherwise documented compatible. This status describes recognized recorded constraints only; extraction completeness is never guaranteed. Protected characteristics, name, account email, school/employer prestige and resume upload status are not ranking inputs. Free text still needs ordinary data-quality review; no broad fairness certification is claimed.

Requirement evidence coverage counts positively evidenced skills plus quantitatively assessable required experience units, divided by identified required/preferred skills, required experience, required formal qualifications and explicit unresolved credential/authorization units. It is null when there are no identified units. A years requirement may be assessable even when the documented lower bound is below it. Coverage is not skill fit, profile completeness, extraction recall, scoring weight or confidence probability. Formal qualification/authorization units remain unsupported pending manual review.

## Reproducibility and limits

Canonical snapshots, sorted child records, SHA-256 fingerprints, explicit configuration and UTC assessment date make calculations reproducible. Time-dependent availability checks use the recorded assessment instant; daily fingerprints prevent indefinite reuse. Identical current input tuples reuse stored IDs/timestamps. Changed input creates history and marks old input stale; failures cannot silently relabel it current.

No independent human relevance labels, calibration, employer feedback or hiring outcomes are available. Narrow taxonomies, lexical role overlap, heuristic experience/extraction, incomplete requirements and normalization limit real-world ranking quality. Human-reviewed labels, coverage-aware ranking, broader validated taxonomy, credential review, privacy retention tooling, scale controls and outcome evaluation remain unimplemented future improvements. Phase 4 has not begun.
