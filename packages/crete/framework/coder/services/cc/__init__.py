"""CC Coder - Uses Claude Agent SDK (Python) instead of CLI binary."""
import asyncio
import subprocess
from pathlib import Path

from claude_agent_sdk import query
from claude_agent_sdk.types import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from python_file_system.directory.context_managers import changed_directory

from crete.commons.interaction.functions import run_command
from crete.framework.agent.functions import store_debug_file
from crete.framework.coder.contexts import CoderContext
from crete.framework.coder.protocols import CoderProtocol


class CCCoder(CoderProtocol):
    """Coder that uses Claude Agent SDK for Python."""

    def __init__(self, max_turns: int = 100, max_budget_usd: float = 5.0):
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd

    def run(self, context: CoderContext, prompt: str) -> bytes | None:
        """Run Claude Agent SDK to generate a fix."""
        with changed_directory(self._agent_context["pool"].source_directory):
            # Restore to clean state
            run_command(("git restore --source=HEAD :/", Path(".")))

            # Run async agent
            diff = asyncio.run(self._run_agent_async(context, prompt))

            if diff is None:
                return None

            return diff.encode()

    async def _run_agent_async(self, context: CoderContext, prompt: str) -> str | None:
        """Run the Claude Agent SDK asynchronously."""
        source_dir = self._agent_context["pool"].source_directory

        # Configure Claude Agent options
        options = ClaudeAgentOptions(
            model="claude-sonnet-4-5-20250929",
            cwd=str(source_dir),
            permission_mode="bypassPermissions",  # Auto-accept all tools
            max_turns=self.max_turns,
            max_budget_usd=self.max_budget_usd,
        )

        messages = []
        assistant_responses = []

        try:
            # Run the agent
            async for message in query(prompt=prompt, options=options):
                messages.append(message)

                # Log the message
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            context["logger"].debug(f"Assistant: {block.text[:200]}...")
                            assistant_responses.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            context["logger"].debug(f"Tool use: {block.name}")

        except Exception as e:
            context["logger"].error(f"Error running Claude Agent SDK: {e}")
            return None

        # Save debug files
        if "output_directory" in context:
            # Save all messages
            messages_file = context["output_directory"] / "cc_messages.txt"
            with open(messages_file, "w") as f:
                for i, msg in enumerate(messages):
                    f.write(f"\n{'='*80}\n")
                    f.write(f"Message {i}: {type(msg).__name__}\n")
                    f.write(f"{'='*80}\n")
                    f.write(f"{msg}\n")

            # Save assistant responses
            responses_file = context["output_directory"] / "cc_responses.txt"
            with open(responses_file, "w") as f:
                for i, response in enumerate(assistant_responses):
                    f.write(f"\n{'='*80}\n")
                    f.write(f"Response {i+1}\n")
                    f.write(f"{'='*80}\n")
                    f.write(f"{response}\n")

        # Get git diff
        diff = self._get_git_diff(source_dir)

        # Restore to clean state
        run_command(("git restore --source=HEAD :/", Path(".")))

        return diff

    def _get_git_diff(self, project_dir: Path) -> str | None:
        """Get git diff from the project directory."""
        try:
            result = subprocess.run(
                ["git", "diff"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except Exception as e:
            return None
