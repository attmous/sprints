import pytest

from workflows.core.prompts import render_prompt_template


def test_render_prompt_template_renders_issue_fields_and_attempt():
    prompt = render_prompt_template(
        prompt_template="Issue: {{ issue.identifier }}\nAttempt: {{ attempt }}",
        variables={"issue": {"identifier": "ISSUE-1"}, "attempt": 2},
    )

    assert prompt == "Issue: ISSUE-1\nAttempt: 2\n"


def test_render_prompt_template_uses_default_and_empty_attempt():
    prompt = render_prompt_template(
        prompt_template="",
        default_template="Issue: {{ issue.identifier }}\nAttempt: {{ attempt }}",
        variables={"issue": {"identifier": "ISSUE-1"}, "attempt": None},
    )

    assert prompt == "Issue: ISSUE-1\nAttempt:\n"


def test_render_prompt_template_json_encodes_nested_values():
    prompt = render_prompt_template(
        prompt_template="Labels: {{ issue.labels }}",
        variables={"issue": {"labels": ["backend", "ready"]}},
    )

    assert prompt == 'Labels: ["backend", "ready"]\n'


def test_render_prompt_template_rejects_unsupported_syntax():
    with pytest.raises(RuntimeError, match="control blocks"):
        render_prompt_template(
            prompt_template="{% if issue %}Issue{% endif %}",
            variables={"issue": {}},
        )
    with pytest.raises(RuntimeError, match="unsupported filter"):
        render_prompt_template(
            prompt_template="{{ issue.title | upper }}",
            variables={"issue": {"title": "Title"}},
        )
    with pytest.raises(RuntimeError, match="unknown variable"):
        render_prompt_template(
            prompt_template="{{ ticket.title }}",
            variables={"issue": {"title": "Title"}},
        )
    with pytest.raises(RuntimeError, match="unbalanced"):
        render_prompt_template(
            prompt_template="{{ issue.title",
            variables={"issue": {"title": "Title"}},
        )
