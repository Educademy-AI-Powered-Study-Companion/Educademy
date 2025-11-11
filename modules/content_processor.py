import logging
import json
import hashlib
from functools import lru_cache
from typing import List

_HAS_LLM = False
try:
    from langchain_community.llms import Ollama
    from langchain_core.prompts import PromptTemplate
    from langchain.chains import LLMChain
    _HAS_LLM = True
    logging.info("content_processor: Ollama/langchain imports available.")
except Exception as e:
    logging.warning("content_processor: Ollama/langchain not available, using fallback summarizer. (%s)", e)

import re
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')

def _split_sentences(text: str) -> List[str]:
    sentences = [s.strip() for s in _SENTENCE_RE.split(text.strip()) if s.strip()]
    return sentences

def _score_sentences(text: str):
    words = re.findall(r'\w+', text.lower())
    if not words:
        return {}
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    maxf = max(freq.values()) if freq else 1
    for k in freq:
        freq[k] = freq[k] / maxf
    sentences = _split_sentences(text)
    scores = {}
    for s in sentences:
        toks = re.findall(r'\w+', s.lower())
        if not toks:
            scores[s] = 0.0; continue
        scores[s] = sum(freq.get(t, 0) for t in toks) / len(toks)
    return scores

def _extractive_summary(text: str, max_sentences: int = 5) -> str:
    if not text or not text.strip():
        return ""
    sentences = _split_sentences(text)
    if len(sentences) <= max_sentences:
        return "\n\n".join(sentences)
    scores = _score_sentences(text)
    ranked = sorted(sentences, key=lambda s: scores.get(s, 0), reverse=True)[:max_sentences]
    chosen = [s for s in sentences if s in ranked]
    return "\n\n".join(chosen)

_llm = None
_chain = None

def _get_llm(streaming=False):
    global _llm
    if _llm is None or streaming:
        try:
            from langchain_community.llms import Ollama
            _llm = Ollama(model="gemma:2b", temperature=0.3)
        except Exception:
            return None
    return _llm

def _get_chain():
    global _chain
    if _chain is None:
        try:
            prompt_template = (
                "You are an expert academic assistant. Provide a comprehensive, detailed summary of the following document.\n\n"
                "DOCUMENT:\n\"{document}\"\n\nDETAILED SUMMARY:\n"
            )
            PROMPT = PromptTemplate(template=prompt_template, input_variables=["document"])
            _chain = LLMChain(llm=_get_llm(), prompt=PROMPT)
        except Exception as e:
            logging.exception("content_processor: failed to build LLMChain: %s", e)
            _chain = None
    return _chain

@lru_cache(maxsize=50)
def _cached_summary(text_hash: str, full_text: str) -> str:
    """
    Try to use LLM chain if available, otherwise fallback to extractive summary.
    """
    try:
        chain = _get_chain()
        if chain is not None:
            result = chain.invoke({"document": full_text})
            if isinstance(result, dict):
                return result.get("text", "") or result.get("result", "") or str(result)
            return str(result)
    except Exception:
        logging.exception("content_processor: LLM summary failed, falling back to extractive summary.")
    return _extractive_summary(full_text, max_sentences=6)

def generate_bullet_point_summary(full_text: str) -> str:
    """
    Primary non-streaming summary API.
    Returns a string (multi-paragraph) summary.
    """
    if not full_text or not full_text.strip():
        return "Error: Cannot summarize empty text."
    text_hash = hashlib.md5(full_text.encode()).hexdigest()
    return _cached_summary(text_hash, full_text)

def generate_summary_stream(full_text: str):
    """
    Streaming summary generator that yields SSE-safe strings like:
      yield "data: {...}\\n\\n"
    If LLM streaming is available it will be used. Otherwise streams an extractive summary
    in chunks (sentence-by-sentence) to preserve the same frontend streaming experience.
    """
    if not full_text or not full_text.strip():
        yield "data: " + json.dumps({"type": "error", "content": "Error: Cannot summarize empty text."}) + "\n\n"
        return

    try:
        chain = _get_chain()
        if chain is not None:
            try:
                yield "data: " + json.dumps({"type": "start"}) + "\n\n"
                for chunk in chain.stream({"document": full_text}):
                    if isinstance(chunk, dict):
                        text_chunk = chunk.get("text") or chunk.get("content") or str(chunk)
                    else:
                        text_chunk = str(chunk)
                    yield "data: " + json.dumps({"type": "chunk", "content": text_chunk}) + "\n\n"
                try:
                    final = chain.invoke({"document": full_text})
                    if isinstance(final, dict):
                        final_text = final.get("text") or final.get("result") or ""
                    else:
                        final_text = str(final)
                    yield "data: " + json.dumps({"type": "done", "full_content": final_text}) + "\n\n"
                except Exception:
                    yield "data: " + json.dumps({"type": "done", "full_content": ""}) + "\n\n"
                return
            except Exception:
                logging.exception("content_processor: LLM streaming failed; falling back to extractive streaming.")
    except Exception:
        logging.exception("content_processor: chain setup failed; falling back to extractive streaming.")

    try:
        yield "data: " + json.dumps({"type": "start"}) + "\n\n"
        summary = _extractive_summary(full_text, max_sentences=6)
        parts = summary.split("\n\n")
        full_so_far = ""
        for p in parts:
            if not p.strip():
                continue
            full_so_far += (p + "\n\n")
            yield "data: " + json.dumps({"type": "chunk", "content": p}) + "\n\n"
        yield "data: " + json.dumps({"type": "done", "full_content": full_so_far.strip()}) + "\n\n"
    except Exception:
        logging.exception("content_processor: fallback streaming error")
        yield "data: " + json.dumps({"type": "error", "content": "Error: Summarization failed."}) + "\n\n"
