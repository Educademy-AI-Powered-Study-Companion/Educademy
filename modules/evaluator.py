import logging, torch
from typing import Tuple, Optional
from sentence_transformers import SentenceTransformer, util
from . import config
_embedding = None
try:
    device = getattr(config, 'DEVICE', None) or ('cuda' if torch.cuda.is_available() else 'cpu')
    _embedding = SentenceTransformer(config.EMBEDDING_MODEL_ID, device=device); _embedding.eval()
    logging.info("Embedding loaded")
except Exception:
    logging.exception("emb load fail"); _embedding = None

def evaluate_student_answer(student_answer: str, reference_summary: str) -> Tuple[float,str]:
    if not _embedding: return 0.0, "Error: grading model unavailable."
    if not student_answer.strip(): return 0.0, "Warning: answer empty."
    with torch.no_grad():
        emb = _embedding.encode([student_answer, reference_summary], convert_to_tensor=True, show_progress_bar=False, normalize_embeddings=True)
        sim = util.pytorch_cos_sim(emb[0].unsqueeze(0), emb[1].unsqueeze(0)).item()
    score = round(max(0,sim)*10,1)
    fb = ("Excellent" if score>8.5 else "Good" if score>6.5 else "Fair" if score>4.0 else "Needs improvement")
    return score, f"{fb}. (Score: {score})"