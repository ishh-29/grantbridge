from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./grantbridge.db"
    auth_secret: str = "local-development-signing-secret-change-before-deployment"
    upload_dir: str = "./private_uploads"
    switch_base_url: str = ""
    switch_agent_id: str = ""
    switch_agent_api_key: str = ""
    switch_agent_name: str = "grantbridge-coordinator"
    switch_agent_names: str = ""
    switch_scout_name: str = "grant-scout"
    switch_eligibility_name: str = "eligibility-analyst"
    switch_writer_name: str = "grant-writer"
    switch_budget_name: str = "budget-analyst"
    switch_compliance_name: str = "compliance-reviewer"


settings = Settings()
