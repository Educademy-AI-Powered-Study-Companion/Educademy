# modules/config.py
"""
Central configuration file for the Educademy application.
This version is optimized to use different Ollama models for different tasks.
"""

# --- Application Settings ---
UPLOAD_DIRECTORY = "uploads"

# --- Logging Configuration ---
LOG_FILE = "app.log"
LOG_LEVEL = "INFO" # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

# --- AI Model IDs ---

# Embedding model for RAG, semantic similarity, and answer evaluation.
# A high-quality model is crucial here.
# Example: "BAAI/bge-large-en-v1.5"
EMBEDDING_MODEL_ID = "BAAI/bge-large-en-v1.5"

# Model for the interactive RAG chatbot.
# Should be a powerful, instruction-following model.
# Example: "mistral", "llama3"
CHATBOT_MODEL_ID = "llama3:8b"

# Model for content processing tasks like summarization and MCQ generation.
# Can be a smaller, faster model.
# Example: "gemma:2b", "phi3"
PROCESSING_MODEL_ID = "gemma:2b"

# --- MCQ Generation Parameters ---
MAX_MCQS_TO_GENERATE = 5

# --- RAG Chain Parameters ---
# Number of relevant chunks to retrieve from the vector store.
TOP_K_RETRIEVED_CHUNKS = 3