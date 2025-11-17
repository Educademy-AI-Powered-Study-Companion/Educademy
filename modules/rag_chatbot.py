import logging
import torch
import hashlib
from typing import Optional, Dict

from langchain_community.llms import Ollama
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from . import config

logger = logging.getLogger(__name__)

class RAGChatbot:
    """A chatbot that uses Ollama and a local RAG pipeline with caching.
    Uses LCEL (LangChain Expression Language) for the chain definition.
    """

    def __init__(self):
        logging.info("Initializing RAG Chatbot with Ollama.")
        
        self.llm = Ollama(
            model=config.CHATBOT_MODEL_ID, 
            temperature=0.2, 
            num_ctx=4096 
        )
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.embedding_model = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL_ID,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True, "batch_size": 32},
        )
        
        self.retriever = None
        self._document_hash: Optional[str] = None
        self._vector_store_cache: Dict[str, FAISS] = {}
        self._prompt_template: Optional[PromptTemplate] = None

        logging.info(f"RAG Chatbot initialized with '{config.CHATBOT_MODEL_ID}' on {device}.")

    def _get_prompt_template(self) -> PromptTemplate:
        if self._prompt_template is None:
            template = """Use the following pieces of context to answer the user's question.
If the answer is not in the context, say you don't know. Do not fabricate answers.

Context:
{context}

Question:
{question}

Helpful Answer:"""
            self._prompt_template = PromptTemplate.from_template(template)
        return self._prompt_template

    def setup_document(self, full_text: str):
        """Process and index a document for RAG with caching."""
        if not full_text or not full_text.strip():
            logging.warning("Empty document passed to setup_document.")
            return

        doc_hash = hashlib.md5(full_text.encode("utf-8")).hexdigest()

        if doc_hash == self._document_hash and doc_hash in self._vector_store_cache:
            logging.info("Reusing cached vector store.")
            self.retriever = self._vector_store_cache[doc_hash].as_retriever(
                search_kwargs={"k": config.TOP_K_RETRIEVED_CHUNKS}
            )
            return

        logging.info(f"Processing new document: {len(full_text)} chars.")
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            add_start_index=True
        )

        chunks = text_splitter.split_text(full_text)
        if not chunks:
            logging.warning("Text splitting produced no chunks.")
            return

        try:
            vector_store = FAISS.from_texts(texts=chunks, embedding=self.embedding_model)
            
            self._vector_store_cache[doc_hash] = vector_store
            if len(self._vector_store_cache) > 5:
                first_key = next(iter(self._vector_store_cache))
                del self._vector_store_cache[first_key]

            self._document_hash = doc_hash
            
            self.retriever = vector_store.as_retriever(
                search_kwargs={"k": config.TOP_K_RETRIEVED_CHUNKS}
            )
            logging.info("Retriever ready.")

        except Exception as e:
            logging.error(f"Failed to create FAISS vector store: {e}", exc_info=True)
            self.retriever = None

    def _format_docs(self, docs) -> str:
        """Helper to format retrieved documents into a single string."""
        return "\n\n".join(doc.page_content for doc in docs)

    def answer_query(self, query: str) -> str:
        """Answer a user's query using LCEL."""
        if self.retriever is None:
            return "I haven't read a document yet. Please upload a file in the chat interface."

        if not query.strip():
            return "Please provide a valid question."

        try:
            rag_chain = (
                {
                    "context": self.retriever | self._format_docs, 
                    "question": RunnablePassthrough()
                }
                | self._get_prompt_template()
                | self.llm
                | StrOutputParser()
            )

            logging.info(f"Invoking chain for query: '{query}'")
            response = rag_chain.invoke(query)
            return response.strip()

        except Exception as e:
            logging.error("Error during RAG chain invocation", exc_info=True)
            return "I encountered an error while processing your request. Ensure Ollama is running."