from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "mcprpc-registry"
    DATABASE_URL: str = "sqlite:///mcprpc_registry.db"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
