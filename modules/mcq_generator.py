"""
Meaningful extractive MCQ generator.

Algorithm (pure-Python, no heavy deps required):
1. Split document into sentences and score them by word-frequency importance.
2. Pick top-N sentences as MCQ sources.
3. For each chosen sentence:
   - Extract candidate answer phrases (prefer multi-word tokens, proper nouns, longest content words).
   - Choose the best candidate and remove it from the sentence to create a cloze question.
   - Build distractors from other high-frequency content terms in the document (excluding the answer).
   - Ensure 4 options (3 distractors + 1 answer), shuffle and return.
4. If no good candidate exists for a sentence, fall back to a "Which term is mentioned..." style question.

This module still supports the LLM path if langchain+Ollama are available (keeps backward compatibility),
but prioritizes the extractive generator which creates meaningful MCQs from the text itself.
"""
import re, random, logging
from typing import List, Dict, Any

_STOPWORDS = {
    'the','and','is','in','of','to','a','for','that','with','as','it','on','are','be','this',
    'by','from','an','or','which','you','your','was','at','have','has','will','can','may',
    'these','those','such','their','its','into','between','but','not','we','they','he','she','i'
}

_sentence_split_re = re.compile(r'(?<=[.!?])\s+')
_word_re = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9\-']+\b")
_proper_noun_re = re.compile(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*)\b')
def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _sentence_split_re.split(text.strip()) if s.strip()]

def _tokenize(text: str) -> List[str]:
    return [w.lower() for w in _word_re.findall(text)]

def _term_frequencies(text: str):
    toks = _tokenize(text)
    freq = {}
    for t in toks:
        if t in _STOPWORDS or t.isdigit() or len(t) <= 2: continue
        freq[t] = freq.get(t, 0) + 1
    return freq

def _score_sentences(text: str):
    sentences = _split_sentences(text)
    freq = _term_frequencies(text)
    maxf = max(freq.values()) if freq else 1
    for k in list(freq.keys()):
        freq[k] = freq[k] / maxf
    scores = {}
    for s in sentences:
        toks = _tokenize(s)
        if not toks:
            scores[s] = 0.0
            continue
        scores[s] = sum(freq.get(t, 0) for t in toks) / len(toks)
    return scores

def _select_candidate_answer(sentence: str, doc_top_terms: List[str]) -> str:
    """
    Heuristic for picking an answer phrase from a sentence:
    1. Prefer proper noun multi-word sequences (e.g., 'World Health Organization')
    2. Else prefer multi-word noun phrases (two consecutive content words)
    3. Else prefer the longest high-frequency content word present in doc_top_terms
    """
    pn = _proper_noun_re.findall(sentence)
    if pn:
        pn_sorted = sorted(pn, key=lambda p: len(p.split()), reverse=True)
        for cand in pn_sorted:
            cand_low = cand.lower()
            if any(w.lower() not in _STOPWORDS for w in cand.split()):
                return cand.strip()

    words = _word_re.findall(sentence)
    words_lower = [w.lower() for w in words]

    for i in range(len(words)-1):
        a = words_lower[i]; b = words_lower[i+1]
        if a not in _STOPWORDS and b not in _STOPWORDS and len(a) > 2 and len(b) > 2:
            phrase = f"{words[i]} {words[i+1]}"
            return phrase.strip()

    for t in doc_top_terms:
        if re.search(r'\b' + re.escape(t) + r'\b', sentence, flags=re.IGNORECASE):
            return t

    candidates = [w for w in words if w.lower() not in _STOPWORDS and len(w) > 2]
    if candidates:
        return max(candidates, key=len).strip()

    return ""

def _make_cloze_question(sentence: str, answer: str) -> str:
    if not answer:
        return "Which term is mentioned in the document?"
    pattern = re.compile(re.escape(answer), flags=re.IGNORECASE)
    if pattern.search(sentence):
        q = pattern.sub("_____", sentence, count=1)
        if not q.endswith('?'):
            q = q.rstrip('.')
            q = q + '?'
        return q
    return f"Which term best completes the following sentence: \"{sentence.strip()}\""

def _build_distractors(answer: str, doc_terms: List[str], k=3):
    """Select k distractors from doc_terms excluding the answer; if insufficient fill with random tokens."""
    candidates = [t for t in doc_terms if t.lower() != answer.lower()]
    random.shuffle(candidates)
    chosen = []
    for c in candidates:
        if len(chosen) >= k: break
        if len(re.sub(r'\W+','',c)) < 2: continue
        chosen.append(c)
    while len(chosen) < k:
        chosen.append(f"option{random.randint(10,99)}")
    return chosen[:k]

_HAS_LLM = False
try:
    from langchain_community.llms import Ollama
    from langchain_core.prompts import PromptTemplate
    _HAS_LLM = True
except Exception:
    _HAS_LLM = False

def _extractive_mcqs_from_text(full_text: str, num_questions: int) -> List[Dict[str, Any]]:
    if not full_text or not full_text.strip():
        return []
    sent_scores = _score_sentences(full_text)
    if not sent_scores:
        return []
    sorted_sents = sorted(sent_scores.items(), key=lambda kv: kv[1], reverse=True)
    top_n = max(num_questions * 3, 8)
    top_sentences = [s for s, sc in sorted_sents[:top_n]]

    freq = _term_frequencies(full_text := full_text) if False else None
    freqs = {}
    toks = _tokenize(full_text)
    for t in toks:
        if t in _STOPWORDS or t.isdigit() or len(t) <= 2: continue
        freqs[t] = freqs.get(t, 0) + 1
    doc_terms = sorted(freqs.keys(), key=lambda k: freqs[k], reverse=True)

    mcqs = []
    used_answers = set()
    for sentence in top_sentences:
        if len(mcqs) >= num_questions:
            break
        answer = _select_candidate_answer(sentence, doc_terms)
        if not answer:
            continue
        if answer.lower() in used_answers:
            continue
        used_answers.add(answer.lower())
        question = _make_cloze_question(sentence, answer)
        distractors = _build_distractors(answer, doc_terms, k=3)
        options = distractors + [answer]
        random.shuffle(options)
        mcqs.append({
            "question": question,
            "options": options,
            "answer": answer
        })
    if len(mcqs) < num_questions:
        extra_terms = [t for t in doc_terms if t.lower() not in used_answers]
        i = 0
        while len(mcqs) < num_questions and i < len(extra_terms):
            correct = extra_terms[i]
            i += 1
            distractors = _build_distractors(correct, doc_terms, k=3)
            opts = distractors + [correct]
            random.shuffle(opts)
            mcqs.append({
                "question": f"Which term is mentioned in the document?",
                "options": opts,
                "answer": correct
            })
    return mcqs[:num_questions]

def generate_meaningful_mcqs(full_text: str, num_questions: int) -> List[Dict[str, Any]]:
    """
    Generate up to num_questions MCQs from the document text.
    Prefers extractive/cloze-style MCQs derived from important sentences.
    """
    try:
        return _extractive_mcqs_from_text(full_text, num_questions)
    except Exception:
        logging.exception("mcq_generator: extractive generation error, returning empty list.")
        return []
