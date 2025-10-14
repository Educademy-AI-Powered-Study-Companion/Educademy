
import logging
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
from . import config 

def generate_bullet_point_summary(full_text: str) -> str:

    logging.info("Generating bullet-point summary with Ollama.")
    if not full_text.strip():
        return "Error: Cannot summarize empty text."
    try:
        llm = Ollama(model=config.PROCESSING_MODEL_ID)
        prompt_template = """
        You are an expert academic assistant. Your task is to provide a high-quality, concise summary of the following document.
        Generate the summary as a list of key bullet points, with each point starting with a '*'.
        
        DOCUMENT:
        "{document}"
        
        BULLET POINT SUMMARY:
        """
        PROMPT = PromptTemplate(template=prompt_template, input_variables=["document"])
        summary_chain = LLMChain(llm=llm, prompt=PROMPT)
        result = summary_chain.invoke({"document": full_text})
        return result.get("text", "Error: Failed to generate summary.").strip()
    except Exception as e:
        logging.error(f"Error during bullet-point summary generation: {e}", exc_info=True)
        return "Error: An issue occurred while generating the summary. Is the Ollama app running?"