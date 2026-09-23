from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "development"
    data_dir: Path = Path("./data")
    rag_working_dir: Path = Path("./rag_storage")
    rag_parser: str = "mineru"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MLS_",
        extra="ignore",
    )
