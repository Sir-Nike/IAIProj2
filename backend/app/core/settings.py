from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    app_name: str = "Indian Multilingual Translation API"
    api_prefix: str = "/api"
    enable_model_download: bool = True
    model_mode: str = "translategemma-image-text-to-text"
    model_id: str = "google/translategemma-4b-it"
    use_safetensors: bool = True
    use_hf_transfer: bool = True
    require_local_model_files: bool = True
    enable_semantic_similarity: bool = True
    semantic_model_id: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    enable_model_tonality: bool = True
    tonality_model_id: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    hf_token_env_var: str = "HF_TOKEN"
    hf_cache_dir: str = str(Path(__file__).resolve().parents[3] / ".hf-cache")
    offload_dir: str = str(Path(__file__).resolve().parents[3] / ".offload")
    max_input_chars: int = 5000
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )


settings = AppSettings()
