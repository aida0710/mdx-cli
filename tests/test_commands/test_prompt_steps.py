from unittest.mock import MagicMock, patch

import pytest
import typer

from mdx_cli.commands._prompt_steps import (
    BACK,
    GoBack,
    Step,
    ask,
    confirm_or_edit,
    run_steps,
)


def _question(answer):
    question = MagicMock()
    question.unsafe_ask.return_value = answer
    return question


def test_ask_returns_answer():
    assert ask(_question("value")) == "value"


def test_ask_raises_go_back_inside_steps():
    """手順の中では、Esc で返る BACK を GoBack にする"""
    raised = []
    answers = iter([BACK, "value"])

    def only_step():
        try:
            ask(_question(next(answers)))
        except GoBack:
            raised.append(True)
            raise

    run_steps([Step("一つ目", only_step)])
    assert raised == [True]


def test_ask_outside_steps_does_not_enable_back():
    """手順の外（項目が1つの選択など）では Esc を割り当てない"""
    question = _question("value")
    original_bindings = question.application.key_bindings
    ask(question)
    assert question.application.key_bindings is original_bindings


def test_run_steps_goes_back_to_previous_step():
    """GoBack が来たら1つ前の項目からやり直す"""
    calls = []
    second_answers = iter([GoBack(), None])

    def first():
        calls.append("first")

    def second():
        calls.append("second")
        outcome = next(second_answers)
        if isinstance(outcome, GoBack):
            raise outcome

    run_steps([Step("一つ目", first), Step("二つ目", second)])
    assert calls == ["first", "second", "first", "second"]


def test_run_steps_stays_on_first_step_when_going_back():
    """最初の項目で戻ろうとしたら、案内を出して同じ項目を聞き直す"""
    outcomes = iter([GoBack(), None])
    calls = []

    def first():
        calls.append("first")
        outcome = next(outcomes)
        if isinstance(outcome, GoBack):
            raise outcome

    run_steps([Step("一つ目", first)])
    assert calls == ["first", "first"]


def test_confirm_or_edit_execute_returns():
    with patch("mdx_cli.commands._prompt_steps.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.return_value = "execute"
        confirm_or_edit([Step("一つ目", lambda: None)], print_summary=lambda: None, message="実行しますか？")


def test_confirm_or_edit_cancel_aborts():
    with patch("mdx_cli.commands._prompt_steps.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.return_value = "cancel"
        with pytest.raises(typer.Abort):
            confirm_or_edit([Step("一つ目", lambda: None)], print_summary=lambda: None, message="実行しますか？")


def test_confirm_or_edit_edit_reruns_from_chosen_step_to_end():
    """「直す」で選んだ項目から最後までを聞き直し、もう一度確認する"""
    calls = []
    steps = [
        Step("一つ目", lambda: calls.append("first")),
        Step("二つ目", lambda: calls.append("second")),
        Step("三つ目", lambda: calls.append("third")),
    ]
    summaries = []
    with patch("mdx_cli.commands._prompt_steps.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.side_effect = ["edit", 1, "execute"]
        confirm_or_edit(steps, print_summary=lambda: summaries.append(1), message="実行しますか？")

    assert calls == ["second", "third"]
    assert len(summaries) == 2


def test_confirm_or_edit_escape_goes_back_to_last_step():
    """確認で Esc を押したら、最後の項目へ戻る"""
    calls = []
    steps = [Step("一つ目", lambda: calls.append("first")), Step("二つ目", lambda: calls.append("second"))]
    with patch("mdx_cli.commands._prompt_steps.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.side_effect = [BACK, "execute"]
        confirm_or_edit(steps, print_summary=lambda: None, message="実行しますか？")

    assert calls == ["second"]


def test_confirm_or_edit_without_steps_offers_only_execute_or_cancel():
    """聞いた項目が無ければ「直す」を出さない"""
    with patch("mdx_cli.commands._prompt_steps.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.return_value = "execute"
        confirm_or_edit([], print_summary=lambda: None, message="実行しますか？")

    values = [choice.value for choice in mock_q.select.call_args.kwargs["choices"]]
    assert values == ["execute", "cancel"]


def test_run_steps_skips_unneeded_steps_in_both_directions():
    """条件に合わない項目は、進むときも戻るときも飛ばす"""
    calls = []
    third_outcomes = iter([GoBack(), None])

    def third():
        calls.append("third")
        outcome = next(third_outcomes)
        if isinstance(outcome, GoBack):
            raise outcome

    steps = [
        Step("一つ目", lambda: calls.append("first")),
        Step("二つ目", lambda: calls.append("second"), is_needed=lambda: False),
        Step("三つ目", third),
    ]
    run_steps(steps)
    assert calls == ["first", "third", "first", "third"]


def test_confirm_or_edit_lists_only_needed_steps():
    steps = [
        Step("一つ目", lambda: None),
        Step("二つ目", lambda: None, is_needed=lambda: False),
    ]
    with patch("mdx_cli.commands._prompt_steps.questionary") as mock_q:
        mock_q.select.return_value.unsafe_ask.side_effect = ["edit", 0, "execute"]
        confirm_or_edit(steps, print_summary=lambda: None, message="実行しますか？")

    edit_choices = mock_q.select.call_args_list[1].kwargs["choices"]
    assert [choice.title for choice in edit_choices] == ["一つ目"]
