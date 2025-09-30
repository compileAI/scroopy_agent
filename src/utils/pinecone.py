from models.source_article import SourceArticle
from utils.settings import GEMINI_API_KEY
from utils.embedding_config import get_config, EmbeddingConfig

from datetime import datetime, timezone
import time
import os
import re
from typing import Dict, List

from pinecone import Pinecone
import pinecone
from sentence_transformers import SentenceTransformer
import torch
from tqdm import tqdm
import tiktoken
from google import genai

from dotenv import load_dotenv
load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
# Initialize Pinecone
pc = Pinecone(PINECONE_API_KEY)

# Initialize Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Global variables for current configuration
current_config: EmbeddingConfig = None
model = None
index = None
tokenizer = None

def initialize_embedding(config_name: str = None):
    """
    Initialize the embedding model and Pinecone index with the specified configuration.
    """
    global current_config, model, index, tokenizer
    
    # Validate API key
    if not PINECONE_API_KEY:
        raise ValueError("Pinecone API key not found in environment variables")
    
    # Get configuration
    current_config = get_config(config_name)
    print(f"Initializing embedding with config: {current_config.model_name}")
    
    # Initialize model based on type
    if current_config.model_name == "meta-llama/Llama-2-7b-chat-hf":
        tokenizer = tiktoken.encoding_for_model("text-embedding-ada-002")
    elif current_config.model_name == "gemini-embedding-001":
        # For Gemini, we don't need to initialize a model
        # The model will be accessed through the Gemini API
        pass
    else:
        # Initialize the SentenceTransformer model for other models
        model = SentenceTransformer(current_config.model_name)
        # Use GPU if available
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model = model.to(device)
    
    try:
        # List all existing indexes
        existing_indexes = pc.list_indexes()
        
        # Check if our index exists
        if current_config.index_name not in [idx.name for idx in existing_indexes]:
            print(f"Index {current_config.index_name} not found. Creating new index...")
            try:
                pc.create_index(
                    name=current_config.index_name,
                    dimension=current_config.dimension,
                    metric="cosine",
                    spec=pinecone.ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"
                    )
                )
                print(f"Successfully created index: {current_config.index_name}")
            except Exception as create_error:
                print(f"Error creating index: {str(create_error)}")
                raise create_error
        
        # Get the index
        index = pc.Index(current_config.index_name)
        print(f"Successfully connected to index: {current_config.index_name}")
        
        # Create default namespace (skip for sparse indexes)
        if not current_config.is_sparse:
            try:
                # Create namespace by upserting a dummy vector with at least one non-zero value
                dummy_vector = {
                    "id": "dummy",
                    "values": [1.0] + [0.0] * (current_config.dimension - 1),  # First value is 1.0, rest are 0.0
                    "metadata": {"created_at": datetime.now(timezone.utc).isoformat()}
                }
                index.upsert(vectors=[dummy_vector], namespace="default")
                
                # Clean up the dummy vector
                index.delete(ids=["dummy"], namespace="default")
            except Exception as e:
                print(f"Error creating namespace: {str(e)}")
                # If the error is not about the namespace already existing, raise it
                if "already exists" not in str(e).lower():
                    raise e
                print("Namespace already exists, continuing...")
        else:
            print("Skipping namespace creation for sparse index (not needed)")
                
    except Exception as e:
        print(f"Error in initialize_embedding: {str(e)}")
        raise e

# Initialize with default configuration
initialize_embedding()

def truncate_text(text: str, max_tokens: int = 500) -> str:
    """Truncate text to a maximum number of tokens"""
    if current_config.model_name == "meta-llama/Llama-2-7b-chat-hf":
        tokens = tokenizer.encode(text)
        if len(tokens) > max_tokens:
            truncated_tokens = tokens[:max_tokens]
            return tokenizer.decode(truncated_tokens)
        return text
    else:
        # For other models, use word-based truncation
        words = text.split()
        if len(words) > max_tokens:
            return ' '.join(words[:max_tokens])
        return text

def chunk_articles(articles: List[SourceArticle]) -> List[Dict]:
    """Prepare chunks from articles, ready for embedding."""
    chunks = []
    for article in articles:
        # Clean and prepare text
        title = article.title or ""
        content = article.content or ""
        
        # Remove extra whitespace and normalize
        title = " ".join(title.split())
        content = " ".join(content.split())
        
        # Format the passage with title and content
        if title and content:
            combined_text = f"{current_config.passage_prefix}Title: {title}\nContent: {content}"
        else:
            combined_text = f"{current_config.passage_prefix}{title}{content}"
        
        # Truncate if too long
        truncated_text = truncate_text(combined_text)

        chunk = {
            "id": article.id,
            "text": truncated_text,
            "metadata": {
                "id": article.id,
                "published": article.published.isoformat() if article.published else "",
                "published_ts": article.published.timestamp() if article.published else 0
            }
        }
        chunks.append(chunk)

    print(f"Chunking complete: {len(chunks)} chunks prepared.")
    return chunks

def get_embeddings(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """Get embeddings using the current model."""
    if current_config.model_name == "meta-llama/Llama-2-7b-chat-hf":
        # Use Pinecone Inference API for Llama
        EMBED_BATCH_SIZE = 50  # Pinecone embedding batch limit
        RETRIES = 3  # Number of retries for failed requests
        sum_tokens = 0
        embeddings = []
        
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch_texts = texts[i:i+EMBED_BATCH_SIZE]
            
            for attempt in range(RETRIES):
                try:
                    # Check rate limit
                    sum_tokens += sum([len(tokenizer.encode(text, allowed_special={"<|endoftext|>"})) for text in batch_texts])
                    if sum_tokens > 200000:
                        sum_tokens = 0
                        print("Rate limit reached. Sleeping for 60 seconds...")
                        time.sleep(60)

                    batch_embeddings = pc.inference.embed(
                        model="llama-text-embed-v2",
                        inputs=batch_texts,
                        parameters={"input_type": "passage"}
                    )
                    embeddings.extend([e["values"] for e in batch_embeddings])
                    break
                except pinecone.exceptions.ServiceException as e:
                    if e.status == 504 and attempt < RETRIES - 1:
                        print("504 Gateway Timeout. Retrying in 10s...")
                        time.sleep(10)
                    else:
                        raise e
    elif current_config.model_name == "gemini-embedding-001":        
        
        # Print overall token count for debugging
        total_chars = sum(len(text) for text in texts)
        print(f"📊 Embedding {len(texts)} texts with ~{total_chars // 4:,} total tokens")
        
        embeddings = []
        for i in tqdm(range(0, len(texts), batch_size), desc="Generating Gemini embeddings"):
            batch = texts[i:i + batch_size]
            batch_success = False
            max_retries = 3
            
            for retry_attempt in range(max_retries):
                try:
                    batch_embeddings = client.models.embed_content(
                        model="gemini-embedding-001",
                        contents=batch,
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=768
                    )
                    embeddings.extend([e.values for e in batch_embeddings.embeddings])
                    batch_success = True
                    break
                    
                except Exception as e:
                    if retry_attempt < max_retries - 1:
                        wait_time = (retry_attempt + 1) * 30  # Exponential backoff: 30s, 60s, 90s
                        print(f"⚠️ Batch {i//batch_size + 1} failed (attempt {retry_attempt + 1}/{max_retries}): {e}")
                        print(f"⏳ Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ Batch {i//batch_size + 1} failed after {max_retries} attempts: {e}")
                        raise e
            
            if not batch_success:
                raise Exception(f"Failed to process batch {i//batch_size + 1} after {max_retries} attempts")
            
            # Add small delay between batches to avoid rate limiting
            if i + batch_size < len(texts):  # Don't delay after the last batch
                time.sleep(0.5)  # 500ms delay between batches
    else:
        # Use SentenceTransformer for other models
        embeddings = []
        for i in tqdm(range(0, len(texts), batch_size), desc="Generating embeddings"):
            batch = texts[i:i + batch_size]
            batch_embeddings = model.encode(
                batch,
                normalize_embeddings=True,
                convert_to_tensor=True,
                show_progress_bar=False
            )
            embeddings.extend(batch_embeddings.cpu().numpy().tolist())
    
    return embeddings

async def embed_articles(chunks: List[Dict]) -> List[Dict]:
    """Embed article chunks using the current model."""
    if not chunks:
        return []

    # Prepare texts (already prefixed in chunk_articles)
    texts = [chunk["text"] for chunk in chunks]
    
    try:
        # Get embeddings for all texts
        embeddings = get_embeddings(texts)
        
        # Combine with original data
        embedded_chunks = []
        for chunk, embedding in zip(chunks, embeddings):
            embedded_chunks.append({
                "id": chunk["id"],
                "embedding": embedding,
                "metadata": chunk["metadata"]
            })
        
        return embedded_chunks

    except Exception as e:
        print(f"Error during embedding process: {e}")
        raise e

async def upload_to_pinecone(embedded_chunks: List[Dict], namespace: str, batch_size: int = 96):
    """Upload embedded chunks to Pinecone with batching."""
    if not embedded_chunks:
        print("No embedded chunks to upload.")
        return

    vectors = []
    for chunk in embedded_chunks:
        vectors.append({
            "id": chunk["id"],
            "values": chunk["embedding"],
            "metadata": chunk["metadata"]
        })

    # Upload in batches
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i+batch_size]
        print(f"Uploading batch {i//batch_size + 1} with {len(batch)} vectors...")
        
        index.upsert(
            vectors=batch,
            namespace=namespace
        )

    print(f"✅ Upload complete: {len(embedded_chunks)} vectors uploaded.")

async def process_and_write_to_pinecone(articles: List[SourceArticle], config_name: str = None):
    """
    Process and write articles to Pinecone.
    Only receives articles that were successfully inserted into Supabase.
    """
    try: 
        if not articles:
            print("No articles to process for Pinecone.")
            return

        # Initialize with specified configuration if provided
        if config_name:
            initialize_embedding(config_name)

        print(f"Processing {len(articles)} articles for Pinecone...")

        # Step 1: Chunk articles
        chunks = chunk_articles(articles)

        # Step 2: Embed articles
        embeddings = await embed_articles(chunks)

        # Step 3: Upload to Pinecone
        await upload_to_pinecone(embeddings, namespace="sourcearticles")
        print(f"✅ Uploaded {len(articles)} articles to Pinecone")
    except Exception as e:
        print(f"Error processing and writing to Pinecone: {e}")
        raise e

    