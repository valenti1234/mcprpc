from mc_automesh import expose, ignore
import sys
import logging

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stderr)

logger = logging.getLogger(__name__)



_COUNTER = 0

@expose(name="billing.counter", tags=["example", "stateful"])
def counter(step: int = 1) -> int:
    global _COUNTER
    _COUNTER += step
    logger.info("event=billing_counter value=%s step=%s", _COUNTER, step)
    return _COUNTER

def calculate_vat(amount: float, rate: float = 0.20) -> float:
    """
    Calculates VAT for a given amount.
    """
    logger.info("event=calculate_vat amount=%s rate=%s", amount, rate)
    return amount * rate

@expose(name="billing.vat", acl={"roles": ["admin"]}, tags=["billing"])
def custom_vat(amount: float) -> float:
    """
    Calculates a custom VAT.
    """
    logger.info("event=custom_vat amount=%s", amount)
    return amount * 0.25

@ignore
def internal_helper() -> bool:
    """
    This function should be ignored because of @ignore.
    """
    return True

def generate_invoice(user_id: int, amount: float) -> str:
    """
    Generates an invoice string.
    """
    logger.info("event=generate_invoice user_id=%s amount=%s", user_id, amount)
    return f"Invoice for user {user_id}: ${amount:.2f}"

def _private_func() -> bool:
    """
    This function should be ignored because it's private.
    """
    return True
