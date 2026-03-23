from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # PostgreSQL
    postgres_user: str = "text2sql"
    postgres_password: str = "text2sql_dev"
    postgres_db: str = "text2sql"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Inference
    inference_mode: str = "mock"  # mock | local | sagemaker
    model_path: str = "seeklhy/OmniSQL-7B"

    # AWS (Phase 3)
    aws_region: str = "us-east-1"
    sagemaker_endpoint_name: str = "omnisql-pg-endpoint"

    # RAG
    embedding_model: str = "all-MiniLM-L6-v2"
    rag_top_k: int = 5

    # Self-correction
    max_correction_attempts: int = 2

    @property
    def database_url(self) -> str:
        base = (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
        if self.postgres_host != "localhost":
            base += "?ssl=require"
        return base

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "protected_namespaces": ("settings_",),
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()