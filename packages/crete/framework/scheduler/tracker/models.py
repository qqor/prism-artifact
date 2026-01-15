from dataclasses import dataclass


@dataclass
class LlmUsage:
    total_cost: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: "LlmUsage") -> "LlmUsage":
        return LlmUsage(
            total_cost=self.total_cost + other.total_cost,
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )

    def __iadd__(self, other: "LlmUsage") -> "LlmUsage":
        self.total_cost += other.total_cost
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        return self