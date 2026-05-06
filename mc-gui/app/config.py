import os


class Settings:
    registry_url: str = os.getenv("REGISTRY_URL", "http://localhost:7000")
    router_url: str = os.getenv("ROUTER_URL", "http://localhost:8001")
    timeout_s: float = float(os.getenv("GUI_TIMEOUT_S", "20.0"))


settings = Settings()
