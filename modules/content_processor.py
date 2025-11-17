import logging
import hashlib
from functools import lru_cache

from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate

from . import config

logger = logging.getLogger(__name__)

_llm_instance = None
_summary_chain = None

def _get_llm():
    """Get or create a shared LLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = Ollama(model=config.PROCESSING_MODEL_ID, temperature=0.3)
    return _llm_instance

def _get_summary_chain():
    """Create modern LCEL chain (prompt | llm)."""
    global _summary_chain
    if _summary_chain is None:
        prompt_template = """
        You are an expert academic assistant. Your task is to provide a high-quality, concise summary of the following document.
        Generate the summary as bullet points, each beginning with '*'.

        DOCUMENT:
        {document}

        BULLET POINT SUMMARY:
        """
        PROMPT = PromptTemplate.from_template(prompt_template)

        _summary_chain = PROMPT | _get_llm()

    return _summary_chain

@lru_cache(maxsize=50)
def _get_cached_summary(text_hash: str, full_text: str) -> str:
    """Cache summaries based on text hash."""
    logger.info("Generating bullet-point summary with Ollama.")
    try:
        chain = _get_summary_chain()

        result = chain.invoke({"document": full_text})
        return result.strip()

    except Exception as e:
        logger.error("Error during summary generation", exc_info=True)
        return "Error: An issue occurred while generating the summary. Is the Ollama app running?"

def generate_bullet_point_summary(full_text: str) -> str:
    """Generate a bullet-point summary with caching."""
    if not full_text.strip():
        return "Error: Cannot summarize empty text."

    text_hash = hashlib.md5(full_text.encode()).hexdigest()
    return _get_cached_summary(text_hash, full_text)