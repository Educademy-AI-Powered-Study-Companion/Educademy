"""
Central configuration file for the Educademy application.
This version is optimized to use different Ollama models for different tasks.
"""

UPLOAD_DIRECTORY = "uploads"

LOG_FILE = "app.log"
LOG_LEVEL = "INFO"

EMBEDDING_MODEL_ID = "BAAI/bge-large-en-v1.5"

CHATBOT_MODEL_ID = "llama3.2"


PROCESSING_MODEL_ID = "llama3.2"

MAX_MCQS_TO_GENERATE = 5

TOP_K_RETRIEVED_CHUNKS = 3