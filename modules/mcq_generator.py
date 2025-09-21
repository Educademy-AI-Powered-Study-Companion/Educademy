# modules/mcq_generator.py
"""
This module uses the powerful Ollama LLM to generate meaningful,
context-aware Multiple Choice Questions from the full text of a document.
"""
import logging
import json
from typing import List, Dict, Any
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from . import config # Use relative import

def generate_meaningful_mcqs(full_text: str, num_questions: int) -> List[Dict[str, Any]]:
    """
    Instructs the Ollama LLM to read a document and generate a list of
    meaningful multiple-choice questions in a structured JSON format.
    """
    logging.info(f"Generating {num_questions} meaningful MCQs with Ollama.")
    if not full_text.strip():
        return []
    try:
        parser = JsonOutputParser()
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
        
        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["document", "num_questions"],
            partial_variables={"format_instructions": parser.get_format_instructions()}
        )
        
        # Use the model ID from the config file
        llm = Ollama(model=config.PROCESSING_MODEL_ID)
        chain = PROMPT | llm | parser
        
        result = chain.invoke({"document": full_text, "num_questions": num_questions})
        
        mcq_list = result.get("questions", [])
        logging.info(f"Successfully generated {len(mcq_list)} MCQs.")
        return mcq_list

    except Exception as e:
        logging.error(f"Error during meaningful MCQ generation: {e}", exc_info=True)
        return []