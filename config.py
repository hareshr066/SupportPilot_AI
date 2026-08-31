import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application configuration settings validated via Pydantic.
    Loads values from environment variables or a local .env file.
    """
    # GitHub Personal Access Token. Can be None for unauthenticated access (low rate limits).
    github_token: Optional[str] = None
    
    # Directory where raw ingested data is saved
    raw_data_dir: str = "./data/raw"
    
    # Directory where processed Silver data is saved
    processed_data_dir: str = "./data/processed"
    
    # PostgreSQL Database Connection URL
    database_url: str = "postgresql+psycopg://postgres:postgres123@localhost:5432/support_triage"
    
    # Data Ingestion & Scaling Configuration
    github_max_issues: int = 1000
    github_max_comments_per_issue: int = 50
    
    # Log level configuration (e.g. DEBUG, INFO, WARNING, ERROR)
    log_level: str = "INFO"

    # AI & Duplicate Detection Configuration
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    cross_encoder_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    duplicate_top_k: int = 20
    duplicate_threshold: float = 0.5
    embedding_batch_size: int = 32

    # Severity / Priority Classification Configuration
    severity_model_name: str = "distilbert-base-uncased"
    severity_max_length: int = 256
    severity_batch_size: int = 16
    severity_learning_rate: float = 2e-5
    severity_epochs: int = 3
    severity_random_seed: int = 42
    severity_model_path: str = "./models/severity/v1"

    # Root-Cause Discovery Configuration
    root_cause_issue_state: str = "closed"
    root_cause_min_text_length: int = 10
    root_cause_umap_neighbors: int = 15
    root_cause_umap_components: int = 10
    root_cause_umap_min_dist: float = 0.1
    root_cause_umap_metric: str = "cosine"
    root_cause_umap_random_state: int = 42
    root_cause_hdbscan_min_cluster_size: int = 15
    root_cause_hdbscan_min_samples: int = 5
    root_cause_max_representative_issues: int = 5
    root_cause_llm_model: str = "gpt-4o-mini"

    # Hybrid Resolution-Relevant Retrieval Configuration
    retrieval_dense_top_k: int = 50
    retrieval_bm25_top_k: int = 50
    retrieval_final_top_k: int = 10
    retrieval_rrf_k: int = 60
    retrieval_dense_weight: float = 0.6
    retrieval_bm25_weight: float = 0.4
    retrieval_repository_scope: str = "same_repository"
    retrieval_bm25_index_dir: str = "./data/retrieval_index"
    retrieval_alpha_evidence: float = 0.3

    # Grounded Resolution Generation Configuration
    resolution_llm_model: str = "gpt-4o-mini"
    resolution_max_cases: int = 8
    resolution_max_chars_per_case: int = 1500
    resolution_max_total_context_chars: int = 12000
    resolution_temperature: float = 0.0
    resolution_max_retries: int = 3
    resolution_prompt_version: str = "resolution_prompt_v1"
    openai_api_key: Optional[str] = None

    # Claim Verification / Resolution Faithfulness Configuration
    verifier_llm_model: str = "gpt-4o-mini"
    verifier_temperature: float = 0.0
    verifier_prompt_version: str = "claim_verifier_v1"
    verifier_snippet_top_k: int = 3
    verifier_snippet_max_chars: int = 1200
    verifier_max_retries: int = 3

    # Calibrated Confidence & Decision Configuration
    confidence_model_version: str = "confidence_model_v1"
    confidence_feature_version: str = "features_v1"
    confidence_threshold_version: str = "threshold_v1"
    confidence_max_false_auto_resolution_rate: float = 0.02
    confidence_default_threshold: float = 0.85
    confidence_model_dir: str = "./data/confidence_models"

    # Routing & Escalation Decision Configuration
    routing_model_version: str = "routing_model_v1"
    routing_min_confidence: float = 0.60
    routing_min_samples_per_component: int = 3
    routing_default_queue: str = "GENERAL_SUPPORT_QUEUE"
    routing_model_dir: str = "./data/routing_models"

    # Pipeline Orchestration Configuration
    pipeline_max_latency: float = 60.0
    pipeline_enable_checkpointing: bool = True
    pipeline_checkpoint_backend: str = "memory"
    pipeline_stage_timeout: float = 30.0
    pipeline_retry_count: int = 2

    # FastAPI API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:8000"
    api_log_level: str = "INFO"
    api_timeout_seconds: float = 60.0
    api_debug: bool = False

    # GitHub Webhook & Sync Configuration
    github_webhook_secret: Optional[str] = "dev_webhook_secret_key_12345"
    github_sync_max_issues: int = 50
    github_sync_include_pull_requests: bool = True
    github_sync_include_comments: bool = True
    github_sync_batch_size: int = 30

    # Pydantic Configuration to read from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Allow extra env vars in system without validation errors
    )

# Instantiate a single global config object to be imported across the application
settings = Settings()
