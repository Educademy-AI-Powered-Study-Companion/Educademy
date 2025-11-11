import logging, hashlib, torch
from langchain_community.llms import Ollama
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from . import config

class RAGChatbot:
    def __init__(self):
        self.llm = Ollama(model=config.CHATBOT_MODEL_ID, temperature=0.2)
        self.embedding = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL_ID, model_kwargs={'device':'cuda' if torch.cuda.is_available() else 'cpu'}, encode_kwargs={'normalize_embeddings':True})
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
        self.qa_chain = RetrievalQA.from_chain_type(llm=self.llm, chain_type="stuff", retriever=self.retriever, chain_type_kwargs={"prompt":self._prompt()}, return_source_documents=False)

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