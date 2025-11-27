from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, RedisDsn, validator

class Settings(BaseSettings):
    PROJECT_NAME: str
    
    # Security
    BACKEND_CORS_ORIGINS: Optional[List[str]] = None
    
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_DRIVER: str
    
    REDIS_URL: RedisDsn
    
    BREEDARCHIVE_USER: str
    
    class Config:
        case_sensitive = True
        env_file = ".env.local"
        from_attributes = True
        extra = "ignore"
    
    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Optional[str]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        if isinstance(v, list):
            return v
        return []
    
    @validator("BACKEND_CORS_ORIGINS", each_item=True)
    def validate_cors_origins(cls, v: str) -> str:
        return v
    
    @property
    def POSTGRES_URL(self) -> str:
        return f"{self.POSTGRES_DRIVER}://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


settings = Settings()

def get_application_info():
    return {
        "project_name": settings.PROJECT_NAME,
        "database_url": settings.POSTGRES_URL,
        "cors_origins": settings.BACKEND_CORS_ORIGINS,
        "redis_url": settings.REDIS_URL,
    }

if __name__ == "__main__":
    info = get_application_info()
    print(f"Project: {info['project_name']}")
    print(f"Database URL: {info['database_url']}") 
    print(f"CORS Origins: {info['cors_origins']}")
    print(f"Redis URL: {info['redis_url']}")
