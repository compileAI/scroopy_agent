from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class EmbeddingConfig:
    model_name: str
    index_name: str
    dimension: int
    query_prefix: str = "query: "
    passage_prefix: str = "passage: "
    is_sparse: bool = False  # True for sparse indexes (BM25), False for dense

# Available configurations
CONFIGS = {
    "bge-large": EmbeddingConfig(
        model_name="BAAI/bge-large-en",
        index_name="scraped-sources2",
        dimension=1024,
        query_prefix="Represent this sentence for searching relevant passages: ",
        passage_prefix="Represent this passage for retrieval: "
    ),
    "llama": EmbeddingConfig(
        model_name="meta-llama/Llama-2-7b-chat-hf",
        index_name="scraped-sources",
        dimension=4096,
        query_prefix="",
        passage_prefix=""
    ),
    "gemini": EmbeddingConfig(
        model_name="gemini-embedding-001",
        index_name="scraped-sources-gemini",
        dimension=768,
        query_prefix="",
        passage_prefix=""
    ),
    "genarticles-sparse": EmbeddingConfig(
        model_name="bm25",
        index_name="genarticle-keyword-search",
        dimension=1,  # Not used for sparse, but required by Pinecone
        query_prefix="",
        passage_prefix="",
        is_sparse=True
    )
}

# Default configuration
DEFAULT_CONFIG = "gemini"

def get_config(config_name: str = None) -> EmbeddingConfig:
    """
    Get the embedding configuration by name.
    If no name is provided, returns the default configuration.
    """
    if config_name is None:
        config_name = DEFAULT_CONFIG
    
    if config_name not in CONFIGS:
        raise ValueError(f"Unknown configuration: {config_name}. Available configs: {list(CONFIGS.keys())}")
    
    return CONFIGS[config_name] 