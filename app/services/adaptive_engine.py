"""Deterministic evidence heuristic, not a calibrated psychometric model."""
from copy import deepcopy


class AdaptiveEngine:
    @staticmethod
    def initial_state(skills: list[str]) -> dict:
        return {s: {'estimated_level': 2.5, 'confidence': 0.15, 'evidence_count': 0} for s in skills}

    @staticmethod
    def update(state: dict, skill: str, evaluation: dict) -> dict:
        result = deepcopy(state)
        item = result[skill]
        n = item['evidence_count']
        # Earlier answers move the estimate faster; clamp to the 1–5 scale.
        alpha = max(0.18, 0.40 / (1 + 0.15 * n))
        item['estimated_level'] = round(max(1, min(5, item['estimated_level'] + alpha *
                                      (evaluation['observed_level'] - item['estimated_level']))), 4)
        item['evidence_count'] += 1
        item['confidence'] = round(min(0.95, 1 - 0.85 * (0.70 ** item['evidence_count'])), 4)
        return result

    @staticmethod
    def rank_questions(questions: list[dict], state: dict, answered: list[str], priorities=None) -> list[tuple]:
        remaining = [q for q in questions if q['id'] not in answered and q['question_type'] != 'Coding']
        if not remaining:
            return []
        # Hard coverage guard: one skill can be at most one answer ahead among available skills.
        minimum = min(state[q['skill']]['evidence_count'] for q in remaining)
        eligible = [q for q in remaining if state[q['skill']]['evidence_count'] == minimum]
        ranked = []
        for q in eligible:
            s = state[q['skill']]
            match = 1 - abs(q['difficulty'] - s['estimated_level']) / 4
            gap = (5 - s['estimated_level']) / 4
            uncertainty = 1 - s['confidence']
            coverage = 1 / (1 + s['evidence_count'])
            priority = (priorities or {}).get(q['skill'], 1)
            score = .42 * match + .20 * gap + .20 * uncertainty + .13 * coverage + .05 * priority
            ranked.append((round(score, 8), q))
        return sorted(ranked, key=lambda pair: (-pair[0], pair[1]['id']))

    def select_question(self, questions, state, answered, priorities=None):
        ranked = self.rank_questions(questions, state, answered, priorities)
        return ranked[0][1] if ranked else None

    @staticmethod
    def termination(assessment: dict, state: dict, count: int, remaining: bool) -> str | None:
        if count >= assessment['max_questions']:
            return 'maximum_questions'
        if count >= max(4, 2 * len(state)) and all(
            s['evidence_count'] >= 2 and s['confidence'] >= assessment['confidence_target'] for s in state.values()
        ):
            return 'confidence_reached'
        if not remaining:
            return 'question_pool_exhausted'
        return None
