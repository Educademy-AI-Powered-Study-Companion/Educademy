
import logging
from sentence_transformers import SentenceTransformer, util
from typing import Tuple, Optional
from . import config 

embedding_model: Optional[SentenceTransformer] = None
try:
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL_ID)
    logging.info(f"Embedding model '{config.EMBEDDING_MODEL_ID}' loaded successfully.")
except Exception as e:
    logging.critical(f"Failed to load embedding model. Error: {e}", exc_info=True)

def evaluate_student_answer(student_answer: str, reference_summary: str) -> Tuple[float, str]:
    if not embedding_model:
        return 0.0, "Error: The grading model is currently unavailable."

    if not student_answer.strip():
        return 0.0, "⚠️ Your answer is empty. Please write something to be graded."

    embedding_student = embedding_model.encode(student_answer, convert_to_tensor=True)
    embedding_reference = embedding_model.encode(reference_summary, convert_to_tensor=True)

    similarity_score = util.pytorch_cos_sim(embedding_student, embedding_reference).item()
    final_score = round(max(0, similarity_score) * 10, 1)

    if final_score > 8.5:
        feedback = f"🌟 Excellent! Your answer is highly relevant. (Score: {final_score})"
    elif final_score > 6.5:
        feedback = f"👍 Good job! You are on the right track. (Score: {final_score})"
    elif final_score > 4.0:
        feedback = f"🤔 Fair attempt. Some key points are missing. (Score: {final_score})"
    else:
        feedback = f"⚡ Needs improvement. Main points are missing. (Score: {final_score})"

    return final_score, feedback