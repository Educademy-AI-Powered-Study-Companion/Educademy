import logging, hashlib, torch
from langchain_community.llms import Ollama
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except Exception:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except Exception:
        import logging as _lg
        _lg.warning("rag_chatbot: langchain text splitter not available; using fallback splitter.")
        class RecursiveCharacterTextSplitter:
            def __init__(self, chunk_size=1000, chunk_overlap=100):
                self.chunk_size = int(chunk_size)
                self.chunk_overlap = int(chunk_overlap)

            def split_text(self, text: str):
                if not text or not text.strip():
                    return []
                text = text.strip()
                if len(text) <= self.chunk_size:
                    return [text]
                chunks = []
                start = 0
                step = self.chunk_size - self.chunk_overlap
                while start < len(text):
                    end = start + self.chunk_size
                    chunks.append(text[start:end])
                    start += max(1, step)
                return chunks
try:
    from langchain.chains import RetrievalQA
except Exception:
    RetrievalQA = None
from langchain_core.prompts import PromptTemplate
from . import config

class RAGChatbot:
    def __init__(self):
        self.llm = Ollama(model=config.CHATBOT_MODEL_ID, temperature=0.2)
        device = getattr(config, 'DEVICE', 'cpu')
        model_kwargs = {'device': device}
        self.embedding = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL_ID, model_kwargs=model_kwargs, encode_kwargs={'normalize_embeddings':True})
        self.retriever = None; self.qa_chain = None; self._doc_hash = None; self._cache = {}
    def _prompt(self):
        return PromptTemplate(template="Context: {context}\nQuestion: {question}\nAnswer:", input_variables=["context","question"])
    def setup_document(self, full_text):
        h = hashlib.md5(full_text.encode()).hexdigest()
        if h == self._doc_hash and h in self._cache:
            self.retriever = self._cache[h].as_retriever(search_kwargs={"k":config.TOP_K_RETRIEVED_CHUNKS}); return
        splitter = RecursiveCharacterTextSplitter(chunk_size=min(1500,max(500,len(full_text)//50)), chunk_overlap=100)
        chunks = splitter.split_text(full_text)
        if not chunks: return
        try:
            vs = FAISS.from_texts(texts=chunks, embedding=self.embedding); self._cache[h] = vs
            if len(self._cache)>5: self._cache.pop(next(iter(self._cache)))
            self.retriever = vs.as_retriever(search_kwargs={"k":config.TOP_K_RETRIEVED_CHUNKS}); self._doc_hash = h
        except Exception:
            logging.exception("faiss")
        if RetrievalQA is not None:
            self.qa_chain = RetrievalQA.from_chain_type(llm=self.llm, chain_type="stuff", retriever=self.retriever, chain_type_kwargs={"prompt":self._prompt()}, return_source_documents=False)
        else:
            class _FallbackRetrievalQA:
                def __init__(self, llm, retriever, prompt_template):
                    self.llm = llm
                    self.retriever = retriever
                    self.prompt_template = prompt_template

                def invoke(self, data: dict):
                    question = data.get("query", "")
                    docs = self.retriever.get_relevant_documents(question)
                    context = "\n\n".join([d.page_content for d in docs[:3]])
                    try:
                        prompt_text = self.prompt_template.format(context=context, question=question)
                    except Exception:
                        prompt_text = f"Context: {context}\nQuestion: {question}\nAnswer:"
                    res = self.llm.invoke(prompt_text)
                    if isinstance(res, dict):
                        return {"result": res.get("text", "") or res.get("result", "") or str(res)}
                    return {"result": str(res)}

            self.qa_chain = _FallbackRetrievalQA(self.llm, self.retriever, self._prompt())

    def answer_query(self, query, use_document=True):
        try:
            if use_document and self.qa_chain:
                res = self.qa_chain.invoke({"query":query}); ans = res.get("result","I couldn't find an answer.")
                if any(x in ans.lower() for x in ["don't know","not mentioned","not in the context"]): return self._general(query)
                return ans
            return self._general(query)
        except Exception:
            logging.exception("answer"); return self._general(query)

    def _general(self, query):
        try:
            prompt = f"You are helpful. Question: {query}\nAnswer:"
            return self.llm.invoke(prompt).strip()
        except Exception:
            logging.exception("general"); return "Error: LLM failed."

    def answer_query_stream(self, query, use_document=True):
        import json
        try:
            if use_document and self.qa_chain and self.retriever:
                docs = self.retriever.get_relevant_documents(query); context = "\n\n".join([d.page_content for d in docs[:3]])
                prompt = f"Context: {context}\nQuestion: {query}\nAnswer:"
                yield f"data: {json.dumps({'type':'start'})}\n\n"
                streamllm = Ollama(model=config.CHATBOT_MODEL_ID, temperature=0.2, streaming=True)
                full = ""
                for chunk in streamllm.stream(prompt):
                    txt = str(chunk); full += txt; yield f"data: {json.dumps({'type':'chunk','content':txt})}\n\n"
                yield f"data: {json.dumps({'type':'done','full_content':full})}\n\n"
            else:
                for chunk in self._general_stream(query): yield chunk
        except Exception:
            logging.exception("stream"); yield f"data: {json.dumps({'type':'error','content':'Error'})}\n\n"

    def _general_stream(self, query):
        import json
        yield f"data: {json.dumps({'type':'start'})}\n\n"
        streamllm = Ollama(model=config.CHATBOT_MODEL_ID, temperature=0.2, streaming=True)
        full = ""
        for chunk in streamllm.stream(f"You are helpful. Question: {query}\nAnswer:"):
            txt = str(chunk); full += txt; yield f"data: {json.dumps({'type':'chunk','content':txt})}\n\n"
        yield f"data: {json.dumps({'type':'done','full_content':full})}\n\n"