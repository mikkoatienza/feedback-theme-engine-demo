"""Token and cost tracking for LLM calls made during a run."""

from __future__ import annotations

from dataclasses import dataclass, field

from feedback_themes.llm import LLM, Completion


@dataclass
class Prices:
    """USD per 1M tokens. Defaults to 0: set real prices from your provider in config."""

    input_per_million: float = 0.0
    output_per_million: float = 0.0


@dataclass
class CostTracker:
    """Wraps an :class:`LLM` and counts tokens across calls."""

    llm: LLM
    prices: Prices = field(default_factory=Prices)
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> Completion:
        """Delegate to the wrapped model and record usage."""
        c = self.llm.complete(prompt, system=system, max_tokens=max_tokens)
        self.calls += 1
        self.input_tokens += c.input_tokens
        self.output_tokens += c.output_tokens
        return c

    @property
    def cost_usd(self) -> float:
        """Estimated cost with the configured prices."""
        return (
            self.input_tokens * self.prices.input_per_million
            + self.output_tokens * self.prices.output_per_million
        ) / 1_000_000
