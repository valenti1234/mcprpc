from mc_automesh import expose, ignore
import sys
import logging

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)

logger = logging.getLogger(__name__)



@expose(name="math.add", tags=["math"])
def add(first: float, second: float) -> float:
    """
    Adds two numbers together.
    """
    logger.info("event=add first=%s second=%s", first, second)
    return first + second

@expose(name="math.subtract", tags=["math"])
def subtract(first: float, second: float) -> float:
    """
    Subtracts two numbers.
    """
    logger.info("event=subtract first=%s second=%s", first, second)
    return first - second   

def _private_func() -> bool:
    """
    This function should be ignored because it's private.
    """
    return True
