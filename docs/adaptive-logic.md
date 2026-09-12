# Adaptive logic — equations, behavior and interpretation

This is an explainable, deterministic evidence heuristic. It is not a calibrated Item Response Theory model and its confidence value is not a statistical probability that a candidate's true skill has been found.

## Initialization

Each configured competency receives independent state:

```json
{"estimated_level":2.5,"confidence":0.15,"evidence_count":0}
```

A competency with no evidence is not treated as a demonstrated 2.5 in the report: the report shows it as not assessed. Initial estimates are priors used only for selection.

## Evaluate the answer

MCQ correctness is exactly 1 or 0, using the stored server-side answer.

The local subjective evaluator checks each rubric concept once using case-insensitive whole-token matching. A concept can contain alternatives separated by `|`; any alternative satisfies that concept. Matching evidence quotes are retained verbatim.

```text
concept_coverage = matched_concepts / total_concepts
completeness = min(1, answer_word_count / rubric_min_words)
correctness = concept_coverage × (0.75 + 0.25 × completeness)
score = 100 × correctness
observed_level = clamp(difficulty − 1 + 2 × correctness, 1, 5)
```

Consequently a lengthy unrelated answer earns zero. A short answer mentioning all concepts receives partial-to-high credit. Keyword repetition does not increase matched-concept count. Semantic errors, negation and keyword stuffing remain limitations; technical accuracy needs expert review.

When an LLM is configured, it supplies rubric correctness plus feedback/evidence. Schema validation and quote checks run before the same score/observed-level transformation. Invalid output or API failure uses the local path. The LLM never chooses the next question.

## Update skill state

Let `n` be the previous evidence count and `L` the previous estimated level:

```text
alpha = max(0.18, 0.40 / (1 + 0.15 × n))
new_level = clamp(L + alpha × (observed_level − L), 1, 5)
new_count = n + 1
new_confidence = min(0.95, 1 − 0.85 × 0.70^new_count)
```

State uses four decimal places. Early evidence has more influence. The confidence schedule is independent of correctness; a candidate who consistently struggles still provides evidence. It does not quantify the reliability of a weak local rubric or conflicting evidence. Confidence must therefore be interpreted with its evidence source and count.

| Observations for a skill | Evidence confidence |
|---:|---:|
| 0 | 0.15 |
| 1 | 0.405 |
| 2 | 0.5835 |
| 3 | 0.7085 |
| 4 | 0.7959 |
| 5 | 0.8571 |

## Choose a question

1. Remove questions already answered during the attempt. Repetition is prohibited, not merely penalized.
2. Exclude coding questions until execution/grading support exists.
3. Among remaining question skills, find the minimum evidence count. Only questions for skills at that count are eligible. This guarantees a balanced first pass and prevents over-testing an available competency. A skill whose question pool is exhausted cannot block progress elsewhere.
4. For every eligible question:

```text
difficulty_match = 1 − abs(difficulty − estimated_level) / 4
skill_gap = (5 − estimated_level) / 4
uncertainty = 1 − confidence
coverage_priority = 1 / (1 + evidence_count)
assessment_priority = configured skill priority (default 1)

selection_score = 0.42 × difficulty_match
                + 0.20 × skill_gap
                + 0.20 × uncertainty
                + 0.13 × coverage_priority
                + 0.05 × assessment_priority
```

5. Sort by descending score and then ascending question UUID for stable tie-breaking.

Relative to a purely soft weighted formula, the coverage guard gives a clear guarantee: when all skills have available questions, no skill is more than one observation ahead. This is an engineering choice, not an empirically validated claim of superior assessment accuracy. Priorities default to equal values; a future recruiter priority editor can modify assessment priorities without changing the engine.

## Worked example

A candidate's Python state starts at level 2.5, confidence 0.15, count 0. Assume a difficulty-3 Python question is selected from the initial tied difficulty range.

**Correct answer:**

```text
correctness = 1
observed_level = 3 − 1 + 2 × 1 = 4
alpha = 0.40
new_level = 2.5 + 0.40 × (4 − 2.5) = 3.1
new_confidence = 1 − 0.85 × 0.70 = 0.405
new_count = 1
```

Other untouched competencies are selected next because of the coverage guard. At the next eligible Python turn, a question near level 3 is preferred. If the level-3 item has already been used and only levels 2 and 4 remain nearby, level 4 is closer to 3.1 and is selected.

**Incorrect answer to the same starting question:**

```text
observed_level = 3 − 1 = 2
new_level = 2.5 + 0.40 × (2 − 2.5) = 2.3
new_confidence = 0.405
```

At the next eligible Python turn, difficulty 2 is preferred. The repository stores different current-question IDs for these trajectories. A regression test runs complete strong and struggling attempts and verifies their paths differ and that the strong path has a greater total difficulty.

## Stop conditions

Evaluated after each accepted answer, in this order:

1. Maximum question limit reached.
2. At least `max(4, 2 × number_of_competencies)` answers, every competency has at least two observations, and every confidence reaches the target.
3. No supported unanswered questions remain.

For the default five-skill assessment and target 0.70, each skill needs three observations (confidence 0.7085). The default maximum is 15, so the cap is reported at 15 because it is checked first. With a higher maximum, confidence can terminate the assessment after 15. A sparse pool can terminate sooner with an explicit exhaustion reason, even below the normal minimum.

## Report and gaps

The overall 0–100 score is the points-weighted mean of answered-question scores, not a conversion of the prior skill estimate. Coverage is the percentage of competencies with at least one observation.

The report includes skill level, confidence, observation count, per-answer evidence, feedback source, strengths, gaps and one interview prompt per competency. Levels below 3 invite exploration of fundamentals; levels at least 3.5 invite deeper trade-off questions. Unobserved competencies are explicitly described as unassessed.

No hiring recommendation, protected-characteristic inference or candidate ranking is generated. Different adaptive paths sample different questions: raw overall scores are not calibrated for between-candidate comparison.


## OpenAI question-generation update

Selection remains deterministic: the engine chooses the skill, difficulty and unused bank slot. OpenAI may supply a new validated question for that slot, informed by the previous answer excerpt, local evaluation and gaps. Thus selection is deterministic, while generated wording is model-dependent. The server persists the full question and answer/rubric snapshot privately on the attempt and records it with the response for auditability. Refreshing does not regenerate the question. The shared bank and its points are unchanged.

MCQs and report follow-ups are local. Written answers use OpenAI grading (240 output-token cap); each new question uses a separate OpenAI generation request (360 output-token cap). There is no report-generation API call. A failed/malformed generation uses the selected bank item and activates a 60-second cooldown. No new question is produced by the LLM when the engine has reached a termination condition. Existing Supabase installations must apply the updated schema and RPC together.


## Latency optimization without changing adaptive decisions

During a written-answer turn, the next evidence count and confidence are known before grading: their formulas do not use correctness. If the hard coverage guard excludes the current competency from the next ranking, every eligible skill estimate is unchanged. In that case, the next selected bank slot is mathematically independent of the pending grade.

The service then grades the submitted answer and generates that independently selected question concurrently. Generation receives the actual answer excerpt, without an invented score. After grading, the normal adaptive engine recomputes and verifies selection before saving the question. When the current skill can participate in the ranking, execution stays sequential. Termination is checked before any parallel generation. No alternative branches are generated and discarded as a normal operation.

The answer, final state and chosen question snapshot still persist together through the existing transaction boundary. Candidate-safe JSON is built from the just-committed state, avoiding redundant database reads. The UI updates the question using that JSON; it does not calculate scores or select questions.
