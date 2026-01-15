"""CCAgent - Claude Code Agent using the Claude Agent SDK (Python)."""
import inspect
from pathlib import Path
from typing import Iterator

from crete.atoms.action import (
    Action,
    CompilableDiffAction,
    NoPatchAction,
    UncompilableDiffAction,
    VulnerableDiffAction,
    WrongDiffAction,
    choose_best_action,
)
from crete.atoms.detection import Detection
from crete.commons.crash_analysis.functions import get_bug_class
from crete.framework.agent.contexts import AgentContext
from crete.framework.agent.functions import store_debug_file
from crete.framework.agent.protocols import AgentProtocol
from crete.framework.coder.services.cc import CCCoder
from crete.framework.insighter.protocols import InsighterProtocol
from crete.framework.insighter.services.crash_log import CrashLogInsighter

CC_USER_PROMPT_TEMPLATE = inspect.cleandoc(
    """
    Create a patch to fix a {bug_class} bug given below and apply it to the code.
    NEVER fix files outside the source directory.
    NEVER do any git operations in or outside the source directory.

    {insights}
    """
).lstrip()

CC_USER_PROMPT_TEMPLATE_WITH_FEEDBACK = inspect.cleandoc(
    """
    I tried to fix a {bug_class} vulnerability causing the crash log in the <crash_log> below.
    I failed to fix the vulnerability with the following patches:

    {failed_patch}

    Explain why the patches failed and provide a new patch to fix the vulnerability.
    Do not repeat the same mistakes in the new patch.
    Try a completely different approach to fix the vulnerability.
    NEVER fix files outside the source directory.
    NEVER do any git operations in or outside the source directory.

    {insights}
    """
).lstrip()

DEFAULT_INSIGHTS_TEMPLATE = inspect.cleandoc(
    """
    Below is the crash log:

    <crash_log>
    {crash_log}
    </crash_log>
    """
).lstrip()

FAILED_PATCH_TEMPLATE = inspect.cleandoc(
    """
    ```diff
    {failed_patch}
    ```

    """
)


class CCAgent(AgentProtocol):
    """Agent using Claude Agent SDK (Python) instead of CLI binary."""

    def __init__(
        self,
        insighters: list[InsighterProtocol] = [],
        max_iterations: int = 3,
        max_turns: int = 100,
        max_budget_usd: float = 5.0,
    ) -> None:
        self._insighters = insighters
        self._max_iterations = max_iterations
        self._max_turns = max_turns
        self._max_budget_usd = max_budget_usd

        self.llm_cost: float = 0.0

    def act(self, context: AgentContext, detection: Detection) -> Iterator[Action]:
        output_directory = (
            context["output_directory"] if "output_directory" in context else None
        )

        failed_patches = ""

        actions: list[Action] = []

        for context in _iterate_with_output_directory(
            context, output_directory, self._max_iterations
        ):
            coder = CCCoder(
                max_turns=self._max_turns, max_budget_usd=self._max_budget_usd
            )
            coder._agent_context = context

            prompt = make_prompt(context, detection, failed_patches)
            diff = coder.run(context, prompt)

            action: Action
            if diff is None or len(diff.strip()) == 0:
                action = NoPatchAction()
            else:
                action = context["evaluator"].evaluate(context, diff, detection)

            store_debug_file(context, "prompt.txt", prompt)
            store_debug_file(
                context,
                "diff.txt",
                diff.decode(errors="replace") if diff is not None else "",
            )

            actions.append(action)

            if isinstance(
                action,
                (
                    VulnerableDiffAction,
                    CompilableDiffAction,
                    UncompilableDiffAction,
                    WrongDiffAction,
                ),
            ):
                failed_patches += FAILED_PATCH_TEMPLATE.format(
                    failed_patch=diff.decode(errors="replace")
                    if diff is not None
                    else ""
                )
            else:
                break

        yield choose_best_action(actions)


def make_prompt(
    context: AgentContext, detection: Detection, failed_patches: str
) -> str:
    bug_class = get_bug_class(context, detection) or ""

    crash_log = CrashLogInsighter().create(context, detection)
    if crash_log is None:
        context["logger"].warning("Failed to generate crash log")
        insights = ""
    else:
        insights = DEFAULT_INSIGHTS_TEMPLATE.format(crash_log=crash_log)

    if failed_patches == "":
        return CC_USER_PROMPT_TEMPLATE.format(
            bug_class=bug_class, insights=insights
        )
    else:
        return CC_USER_PROMPT_TEMPLATE_WITH_FEEDBACK.format(
            bug_class=bug_class, insights=insights, failed_patch=failed_patches
        )


def _iterate_with_output_directory(
    context: AgentContext, output_directory: Path | None, max_iterations: int
) -> Iterator[AgentContext]:
    original_output_directory = context.get("output_directory", None)
    try:
        for i in range(max_iterations):
            if output_directory is not None:
                context["output_directory"] = output_directory / f"iter_{i}"
                context["output_directory"].mkdir(parents=True, exist_ok=True)
            yield context
    finally:
        if original_output_directory is not None:
            context["output_directory"] = original_output_directory
        else:
            context.pop("output_directory", None)
