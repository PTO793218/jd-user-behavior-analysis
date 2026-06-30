from __future__ import annotations

from collections.abc import MutableMapping


QUESTION_INPUT_KEY = "question_input"


def set_question_from_sample(state: MutableMapping[str, str], sample: str) -> str:
    state[QUESTION_INPUT_KEY] = sample
    return sample


def get_current_question(state: MutableMapping[str, str], default_question: str) -> str:
    if QUESTION_INPUT_KEY not in state:
        state[QUESTION_INPUT_KEY] = default_question
    return state[QUESTION_INPUT_KEY]
