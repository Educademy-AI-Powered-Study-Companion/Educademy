import logging
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
from . import config 
import hashlib
from functools import lru_cache

_llm_instance = None
_summary_chain = None

def _get_llm():
    """Get or create a shared LLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = Ollama(model=config.PROCESSING_MODEL_ID, temperature=0.3)
    return _llm_instance

def _get_summary_chain():
    """Get or create a shared summary chain."""
    global _summary_chain
    if _summary_chain is None:
        prompt_template = """
        You are an expert academic assistant. Your task is to provide a high-quality, concise summary of the following document.
        Generate the summary as a list of key bullet points, with each point starting with a '*'.
        
        DOCUMENT:
        "{document}"
        
        BULLET POINT SUMMARY:
        """
        PROMPT = PromptTemplate(template=prompt_template, input_variables=["document"])
        _summary_chain = LLMChain(llm=_get_llm(), prompt=PROMPT)
    return _summary_chain

@lru_cache(maxsize=50)
def _get_cached_summary(text_hash: str, full_text: str) -> str:
    """Cache summaries based on text hash."""
    logging.info("Generating bullet-point summary with Ollama.")
    try:
        summary_chain = _get_summary_chain()
        result = summary_chain.invoke({"document": full_text})
        return result.get("text", "Error: Failed to generate summary.").strip()
    except Exception as e:
        logging.error(f"Error during bullet-point summary generation: {e}", exc_info=True)
        return "Error: An issue occurred while generating the summary. Is the Ollama app running?"

def generate_bullet_point_summary(full_text: str) -> str:
    """Generate a bullet-point summary with caching."""
    if not full_text.strip():
        return "Error: Cannot summarize empty text."
    
    text_hash = hashlib.md5(full_text.encode()).hexdigest()
    return _get_cached_summary(text_hash, full_text)