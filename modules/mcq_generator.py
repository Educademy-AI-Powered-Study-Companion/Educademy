import logging
import re
import hashlib
import json
import requests
from typing import List, Dict, Any
from . import config

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"

def _generate_raw_text_direct(full_text: str, num_questions: int) -> str:
    """
    Connects directly to Ollama without LangChain.
    """
    prompt = f"""
    You are a quiz generator. Create exactly {num_questions} multiple-choice questions based on the text below.

    RULES:
    1. Use this EXACT format for every question.
    2. Separate questions with "###".
    3. Do NOT use Markdown (no bold, no italics).
    4. The 'Answer' line must contain the exact text of the correct option.

    FORMAT EXAMPLE:
    ###
    Q: What is the capital of France?
    A) London
    B) Paris
    C) Berlin
    D) Madrid
    Answer: Paris
    ###

    TEXT TO QUIZ:
    "{full_text[:3500]}"  
    """

    model_to_use = getattr(config, 'CHATBOT_MODEL_ID', 'llama3.2')
    
    payload = {
        "model": model_to_use,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096
        }
    }

    logger.info(f"Sending request to Ollama ({model_to_use})...")
    print(f"--- DEBUG: Contacting Ollama at {OLLAMA_URL} with model {model_to_use} ---")

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        
        if response.status_code == 200:
            response_json = response.json()
            raw_response = response_json.get("response", "")
            print("--- DEBUG: Received response from Ollama ---")
            return raw_response
        else:
            logger.error(f"Ollama API Error: {response.status_code} - {response.text}")
            print(f"--- ERROR: Ollama API returned status {response.status_code} ---")
            return ""
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to Ollama: {e}")
        print(f"--- DEBUG ERROR: Could not connect to Ollama. Is it running? {e} ---")
        return ""

def _scavenge_mcqs_from_text(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parses the text looking for Q/A patterns regardless of formatting.
    """
    mcqs = []
    clean_text = re.sub(r'\*\*|\*', '', raw_text)
    blocks = re.split(r'###|\n\s*\n', clean_text)
    
    for block in blocks:
        if not block.strip(): continue
            
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        question, options, answer = "", [], ""
        
        for line in lines:
            if re.match(r'^(Q:|Question:|\d+[\.:])', line, re.IGNORECASE) or line.endswith('?'):
                question = re.sub(r'^(Q:|Question:|\d+[\.:])\s*', '', line, flags=re.IGNORECASE).strip()
            elif re.match(r'^([A-D1-4][\)\.]|-)\s+', line):
                options.append(re.sub(r'^([A-D1-4][\)\.]|-)\s+', '', line).strip())
            elif line.lower().startswith("answer:"):
                answer = line.split(":", 1)[1].strip()

        if question and len(options) >= 2:
            while len(options) < 4: options.append("None of the above")
            
            final_answer = answer
            if len(answer) == 1 and answer.upper() in "ABCD":
                idx = "ABCD".index(answer.upper())
                if idx < len(options): final_answer = options[idx]
            
            if final_answer not in options:
                matches = [o for o in options if final_answer in o or o in final_answer]
                final_answer = matches[0] if matches else options[0]

            mcqs.append({"question": question, "options": options[:4], "answer": final_answer})

    return mcqs

def generate_meaningful_mcqs(full_text: str, num_questions: int) -> List[Dict[str, Any]]:
    """
    Main function called by app.py
    """
    if not full_text or not full_text.strip():
        return []
    
    raw_text = _generate_raw_text_direct(full_text, num_questions)
    
    if not raw_text:
        return [{
            "question": "System Error: Could not connect to Ollama.",
            "options": ["Is Ollama running?", "Is the model correct in config?", "Check Terminal", "Retry"],
            "answer": "Is Ollama running?"
        }]

    mcqs = _scavenge_mcqs_from_text(raw_text)
    
    if not mcqs:
        return [{
            "question": "Error: The AI generated text but we couldn't find any questions.",
            "options": ["Try simpler text", "Check formatting", "Retry", "Ignore"],
            "answer": "Retry"
        }]
        
    return mcqs