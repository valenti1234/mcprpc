import os

class Settings:
    registry_url: str = os.getenv("REGISTRY_URL", "http://localhost:7000")
    registry_timeout_s: float = float(os.getenv("REGISTRY_TIMEOUT_S", "5.0"))
    router_timeout_s: float = float(os.getenv("ROUTER_TIMEOUT_S", "15.0"))

    retry_attempts: int = int(os.getenv("ROUTER_RETRY_ATTEMPTS", "3"))
    retry_base_delay_s: float = float(os.getenv("ROUTER_RETRY_BASE_DELAY_S", "0.2"))
    retry_max_delay_s: float = float(os.getenv("ROUTER_RETRY_MAX_DELAY_S", "2.0"))

    cb_failure_threshold: int = int(os.getenv("ROUTER_CB_FAILURE_THRESHOLD", "5"))
    cb_recovery_timeout_s: float = float(os.getenv("ROUTER_CB_RECOVERY_TIMEOUT_S", "30.0"))
    cb_half_open_successes: int = int(os.getenv("ROUTER_CB_HALF_OPEN_SUCCESSES", "2"))

    stdio_persistent: bool = os.getenv("MCPRPC_STDIO_PERSISTENT", "1").strip().lower() in ("1", "true", "yes")
    stdio_idle_timeout_s: float = float(os.getenv("MCPRPC_STDIO_IDLE_TIMEOUT_S", "60"))
    stdio_reap_interval_s: float = float(os.getenv("MCPRPC_STDIO_REAP_INTERVAL_S", "5"))
    stdio_max_sessions: int = int(os.getenv("MCPRPC_STDIO_MAX_SESSIONS", "64"))

settings = Settings()
