from typing import Any, Callable, TypeAlias, Union

import litellm
from litellm import CustomStreamWrapper
from litellm.types.utils import ModelResponse

from crete.framework.scheduler.tracker.models import LlmUsage
from crete.framework.scheduler.tracker.protocols import TrackerProtocol

# Define a type alias for the completion function
CompletionCallable: TypeAlias = Callable[..., Union[ModelResponse, CustomStreamWrapper]]


class LlmCostTracker(TrackerProtocol):
    def __init__(self, max_cost: float, block_llm: bool = False) -> None:
        self._max_cost = max_cost
        self._total_usage: LlmUsage = LlmUsage()
        self._current_usage: LlmUsage = LlmUsage()
        self._original_completion: CompletionCallable
        self._block_llm = block_llm

    def is_exhausted(self) -> bool:
        return self._total_usage.total_cost >= self._max_cost

    def start(self) -> None:
        self._original_completion = litellm.completion  # pyright: ignore[reportUnknownMemberType]
        litellm.completion = self._tracking_completion

    def stop(self) -> None:
        litellm.completion = self._original_completion

    def _tracking_completion(
        self, *args: Any, **kwargs: Any
    ) -> Union[ModelResponse, CustomStreamWrapper]:
        if self._block_llm and self.is_exhausted():
            raise Exception(f"{__class__.__name__}: LLM cost limit exceeded, aborting")
        response = self._original_completion(*args, **kwargs)
        self._update_usage(response)
        return response

    def _update_usage(
        self, response: Union[ModelResponse, CustomStreamWrapper]
    ) -> None:
        if not isinstance(response, ModelResponse):
            return

        try:
            self._current_usage = _litellm_usage_from_response(response)
            self._total_usage += self._current_usage
        except Exception:
            return


def _litellm_cost_from_usage(model: str, usage: LlmUsage) -> float:
    prompt_cost, completion_cost = litellm.cost_per_token(  # pyright: ignore[reportUnknownMemberType, reportPrivateImportUsage]
        model=model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )
    return prompt_cost + completion_cost


def _litellm_usage_from_response(response: ModelResponse) -> LlmUsage:
    if "usage" not in response:
        raise ValueError("Response does not contain usage")

    usage = LlmUsage(
        prompt_tokens=response["usage"]["prompt_tokens"],
        completion_tokens=response["usage"]["completion_tokens"],
    )
    usage.total_cost = _litellm_cost_from_usage(model=response["model"], usage=usage)

    return usage
