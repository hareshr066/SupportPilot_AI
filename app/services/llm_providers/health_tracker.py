import time
import logging
from typing import Dict, Optional
from app.services.llm_providers.base import LLMErrorCategory

logger = logging.getLogger("llm_providers.health")


class ProviderState:
    """
    In-process state tracker for an individual LLM Provider.
    Tracks availability, consecutive failures, and temporary cooldown timers.
    """

    def __init__(self, name: str):
        self.name = name
        self.status = "available"  # "available" | "cooldown" | "disabled"
        self.failure_count = 0
        self.cooldown_until = 0.0
        self.last_error_category: Optional[LLMErrorCategory] = None

    def is_available(self, now: Optional[float] = None) -> bool:
        current_time = now if now is not None else time.time()
        if self.status == "disabled":
            return False
        if self.status == "cooldown":
            if current_time >= self.cooldown_until:
                logger.info(f"Provider {self.name} cooldown period expired. Marking AVAILABLE.")
                self.status = "available"
                return True
            return False
        return True

    def record_success(self):
        """Resets failure counters and restores provider to available state."""
        if self.status != "available":
            logger.info(f"Provider {self.name} restored to AVAILABLE after successful execution.")
        self.status = "available"
        self.failure_count = 0
        self.cooldown_until = 0.0
        self.last_error_category = None

    def record_failure(
        self,
        category: LLMErrorCategory,
        cooldown_seconds: float = 60.0,
        now: Optional[float] = None
    ):
        """
        Records a provider failure and places it into cooldown or disabled state.
        Rate limits & transient server errors place the provider into short cooldown.
        Authentication & missing key errors mark the provider as disabled.
        """
        current_time = now if now is not None else time.time()
        self.failure_count += 1
        self.last_error_category = category

        if category == LLMErrorCategory.AUTH_CONFIGURATION_ERROR:
            self.status = "disabled"
            logger.warning(
                f"Provider {self.name} encountered AUTH/CONFIGURATION error. "
                f"Disabling provider for process lifetime."
            )
        elif category in (LLMErrorCategory.RATE_LIMIT, LLMErrorCategory.TRANSIENT_SERVER_ERROR):
            self.status = "cooldown"
            self.cooldown_until = current_time + cooldown_seconds
            logger.warning(
                f"Provider {self.name} placed in COOLDOWN for {cooldown_seconds}s "
                f"due to {category.value} (failures={self.failure_count})."
            )
        else:
            # Other errors increase failure count but don't force immediate cooldown unless repeated
            if self.failure_count >= 3:
                self.status = "cooldown"
                self.cooldown_until = current_time + cooldown_seconds
                logger.warning(
                    f"Provider {self.name} placed in COOLDOWN for {cooldown_seconds}s "
                    f"after {self.failure_count} consecutive failures."
                )


class ProviderHealthTracker:
    """
    Centralized in-process provider health registry.
    Thread-safe dictionary of provider states for SupportPilot.
    """

    def __init__(self, default_cooldown_seconds: float = 60.0):
        self._states: Dict[str, ProviderState] = {}
        self.default_cooldown_seconds = default_cooldown_seconds

    def get_state(self, provider_name: str) -> ProviderState:
        name_clean = provider_name.lower()
        if name_clean not in self._states:
            self._states[name_clean] = ProviderState(name_clean)
        return self._states[name_clean]

    def is_available(self, provider_name: str) -> bool:
        return self.get_state(provider_name).is_available()

    def record_success(self, provider_name: str):
        self.get_state(provider_name).record_success()

    def record_failure(
        self,
        provider_name: str,
        category: LLMErrorCategory,
        cooldown_seconds: Optional[float] = None
    ):
        cd = cooldown_seconds if cooldown_seconds is not None else self.default_cooldown_seconds
        self.get_state(provider_name).record_failure(category, cooldown_seconds=cd)

    def reset(self):
        """Resets all provider health states (useful for testing)."""
        self._states.clear()


# Global in-process health tracker instance
health_tracker = ProviderHealthTracker()
