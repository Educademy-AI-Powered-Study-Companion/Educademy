
import logging
import torch
import hashlib
from langchain_community.llms import Ollama
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from . import config

class RAGChatbot:
    """A chatbot that uses Ollama and a local RAG pipeline with caching."""
    def __init__(self):
        logging.info("Initializing RAG Chatbot with Ollama.")
        self.llm = Ollama(model=config.CHATBOT_MODEL_ID, temperature=0.2)
        self.embedding_model = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL_ID,
            model_kwargs={'device': 'cuda' if torch.cuda.is_available() else 'cpu'},
            encode_kwargs={'normalize_embeddings': True, 'batch_size': 32}
        )
        self.retriever = None
        self.qa_chain = None
        self._document_hash = None
        self._vector_store_cache = {}
        self._prompt_template = None
        logging.info(f"RAG Chatbot initialized to use Ollama model '{config.CHATBOT_MODEL_ID}'.")

    def _get_prompt_template(self):
        """Get or create prompt template."""
        if self._prompt_template is None:
            self._prompt_template = PromptTemplate(
                template="""Use the following pieces of context to answer the user's question.
If you don't know the answer from the context, just say that you don't know. Do not try to make up an answer.

Context: {context}
Question: {question}

Helpful Answer:""",
                input_variables=["context", "question"]
            )
        return self._prompt_template

    def setup_document(self, full_text: str):
        """Processes and indexes a document for RAG with caching."""
        doc_hash = hashlib.md5(full_text.encode()).hexdigest()
        
        if doc_hash == self._document_hash and doc_hash in self._vector_store_cache:
            logging.info("Reusing cached vector store for same document.")
            self.retriever = self._vector_store_cache[doc_hash].as_retriever(
                search_kwargs={"k": config.TOP_K_RETRIEVED_CHUNKS}
            )
        else:
            logging.info(f"Setting up RAG for a document of {len(full_text)} characters.")
            chunk_size = min(1500, max(500, len(full_text) // 50))
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, 
                chunk_overlap=min(200, chunk_size // 5)
            )
            chunks = text_splitter.split_text(full_text)
            if not chunks:
                logging.warning("Text splitting resulted in no chunks.")
                return
            try:
                vector_store = FAISS.from_texts(texts=chunks, embedding=self.embedding_model)
                self._vector_store_cache[doc_hash] = vector_store
                if len(self._vector_store_cache) > 5:
                    oldest_key = next(iter(self._vector_store_cache))
                    del self._vector_store_cache[oldest_key]
                
                self.retriever = vector_store.as_retriever(
                    search_kwargs={"k": config.TOP_K_RETRIEVED_CHUNKS}
                )
                self._document_hash = doc_hash
                logging.info("FAISS vector store and retriever created successfully.")
            except Exception as e:
                logging.error(f"Failed to create FAISS vector store. Error: {e}", exc_info=True)
                return
        
        PROMPT = self._get_prompt_template()
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.retriever,
            chain_type_kwargs={"prompt": PROMPT},
            return_source_documents=False
        )
        logging.info("RAG chain has been created and is ready.")

    def answer_query(self, query: str) -> str:
        """Answers a user's query using the fully configured RAG chain."""
        if not self.qa_chain:
            return "The document has not been processed yet or an error occurred during setup."
        logging.info(f"Invoking RAG chain with query: '{query}'")
        try:
            result = self.qa_chain.invoke({"query": query})
            return result.get("result", "I could not find an answer.")
        except Exception as e:
            logging.error(f"Error during RAG chain invocation: {e}", exc_info=True)
            return "An error occurred while generating the answer. Make sure your Ollama app is running."