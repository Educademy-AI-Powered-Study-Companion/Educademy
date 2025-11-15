import logging
import json
from typing import List, Dict, Any
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from . import config
import hashlib
from functools import lru_cache

_parser = JsonOutputParser()
_prompt_template = None
_llm_instance = None

def _get_llm():
    """Get or create a shared LLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = Ollama(model=config.PROCESSING_MODEL_ID, temperature=0.5)
    return _llm_instance

def _get_prompt():
    """Get or create a shared prompt template."""
    global _prompt_template
    if _prompt_template is None:
        prompt_template = """
        You are an expert educator creating a quiz. Based on the following document, generate exactly {num_questions} multiple-choice questions to test comprehension.

        **CRITICAL INSTRUCTIONS:**
        - Your output MUST be a single, valid JSON object.
        - The JSON object must have a single key called "questions", which is a list of question objects.
        - Each object in the list must have exactly three keys:
          1. "question": A string containing the question text.
          2. "options": A list of exactly 4 strings (3 incorrect, 1 correct).
          3. "answer": A string that is an exact copy of the correct option.
        - Do not add any text or explanations before or after the JSON object.

        DOCUMENT:
        "{document}"

        {format_instructions}
        """
        _prompt_template = PromptTemplate(
            template=prompt_template,
            input_variables=["document", "num_questions"],
            partial_variables={"format_instructions": _parser.get_format_instructions()}
        )
    return _prompt_template

@lru_cache(maxsize=50)
def _get_cached_mcqs(text_hash: str, full_text: str, num_questions: int) -> List[Dict[str, Any]]:
    """Cache MCQs based on text hash and number of questions."""
    logging.info(f"Generating {num_questions} meaningful MCQs with Ollama.")
    try:
        PROMPT = _get_prompt()
        llm = _get_llm()
        chain = PROMPT | llm | _parser
        
        result = chain.invoke({"document": full_text, "num_questions": num_questions})
        mcq_list = result.get("questions", [])
        logging.info(f"Successfully generated {len(mcq_list)} MCQs.")
        return mcq_list
    except Exception as e:
        logging.error(f"Error during meaningful MCQ generation: {e}", exc_info=True)
        return []

def generate_meaningful_mcqs(full_text: str, num_questions: int) -> List[Dict[str, Any]]:
    """Generate MCQs with caching."""
    if not full_text.strip():
        return []
    
    text_hash = hashlib.md5(f"{full_text}_{num_questions}".encode()).hexdigest()
    return _get_cached_mcqs(text_hash, full_text, num_questions)