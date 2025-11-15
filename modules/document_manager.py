import hashlib, logging
from datetime import datetime
from typing import Optional, Dict

class DocumentManager:
    def __init__(self, max_docs=50):
        self._docs: Dict[str, Dict] = {}; self._max = max_docs
    def store_document(self, text: str, filename: Optional[str]=None, metadata: Optional[Dict]=None)->str:
        if not text or not text.strip(): raise ValueError("Empty")
        h=hashlib.md5(text.encode()).hexdigest()
        self._docs[h]={'text':text,'filename':filename or 'untitled','hash':h,'timestamp':datetime.utcnow(),'size':len(text),'metadata':metadata or {}}
        if len(self._docs)>self._max:
            oldest=min(self._docs.keys(), key=lambda k:self._docs[k]['timestamp']); del self._docs[oldest]; logging.info("Evicted %s",oldest[:8])
        logging.info("Stored %s",h[:8]); return h
    def get_document(self,h): return self._docs.get(h)
    def get_document_text(self,h): d=self._docs.get(h); return d['text'] if d else None
    def list_documents(self): return [{'hash':d['hash'],'filename':d['filename'],'size':d['size'],'timestamp':d['timestamp'].isoformat()} for d in self._docs.values()]
    def get_stats(self):
        if not self._docs: return {'total_documents':0,'total_size':0}
        sizes=[d['size'] for d in self._docs.values()]; ts=[d['timestamp'] for d in self._docs.values()]
        return {'total_documents':len(self._docs),'total_size':sum(sizes),'average_size':sum(sizes)//len(sizes),'oldest_timestamp':min(ts).isoformat(),'newest_timestamp':max(ts).isoformat()}
document_manager = DocumentManager()
