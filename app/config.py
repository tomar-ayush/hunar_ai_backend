from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Environment: "development", "staging", "production"
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost/dbname"

    # Celery / Redis
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Apollo.IO People Search API
    APOLLO_API_KEY: str = ""
    APOLLO_BASE_URL: str = "https://api.apollo.io/api/v1"

    # GitHub API (Optional, raises rate limit from 60 to 5,000 req/hr)
    GITHUB_TOKEN: str = ""

    # Hunar.AI Voice API (Official external/v1 API)
    HUNAR_API_KEY: str = ""
    HUNAR_BASE_URL: str = "https://api.voice.hunar.ai/external/v1"
    HUNAR_AGENT_ID: str = ""
    HUNAR_CALLBACK_BASE_URL: str = ""  # e.g., https://your-domain.com or ngrok URL

    # Google Gemini LLM
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"


settings = Settings()
