from mc_automesh import expose, ignore
import sys
import logging

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)

logger = logging.getLogger(__name__)



_COUNTER = 0

def reset_counter() -> None:
    global _COUNTER
    _COUNTER = 0
    logger.info("event=testing_counter_reset")

def calculator(a: int, operator: str, b: int) -> int:
    if operator == "+":
        return a + b
    elif operator == "-":
        return a - b
    elif operator == "*":
        return a * b
    elif operator == "/":
        return a / b
    else:
        raise ValueError(f"Invalid operator: {operator}")



def counter(step: int = 1) -> int:
    global _COUNTER
    _COUNTER += step
    logger.info("event=testing_counter value=%s step=%s", _COUNTER, step)
    return _COUNTER

def _private_func() -> bool:
    """
    This function should be ignored because it's private.
    """
    return True
