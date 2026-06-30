from agent_app.ui_state import (
    QUESTION_INPUT_KEY,
    get_current_question,
    set_question_from_sample,
)


def test_selecting_sample_updates_question_input_state():
    state = {}

    selected = set_question_from_sample(state, "负面评论主要集中在哪些方面？")

    assert selected == "负面评论主要集中在哪些方面？"
    assert state[QUESTION_INPUT_KEY] == "负面评论主要集中在哪些方面？"
    assert get_current_question(state, "默认问题") == "负面评论主要集中在哪些方面？"


def test_current_question_initializes_from_default_when_missing():
    state = {}

    question = get_current_question(state, "为什么浏览量高但购买少？")

    assert question == "为什么浏览量高但购买少？"
    assert state[QUESTION_INPUT_KEY] == "为什么浏览量高但购买少？"
