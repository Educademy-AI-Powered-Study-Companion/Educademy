import os, json, logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_compress import Compress
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from modules import content_processor, mcq_generator, evaluator, utils, rag_chatbot, config
from modules.document_manager import document_manager

app = Flask(__name__); Compress(app)
app.config.update(UPLOAD_FOLDER=config.UPLOAD_DIRECTORY, MAX_CONTENT_LENGTH=16*1024*1024, SEND_FILE_MAX_AGE_DEFAULT=31536000)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
bot = rag_chatbot.RAGChatbot()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client.get_database(os.getenv("MONGO_DBNAME", "EduMentorDB"))
    students_collection = db["students"]; students_collection.create_index([("student", 1), ("timestamp", -1)])
    logging.info("Mongo ok")
except Exception:
    logging.exception("Mongo fail"); client = db = students_collection = None

def sse_headers(): return {"Content-Type":"text/event-stream","Cache-Control":"no-cache, no-transform","X-Accel-Buffering":"no","Connection":"keep-alive"}
def make_sse(data): return f"data: {json.dumps(data)}\n\n"

@app.route('/') 
def home(): return render_template('StudentHome.html')
@app.route('/summary') 
def summary_page(): return render_template('Summarizer.html')
@app.route('/mcq') 
def mcq_page(): return render_template('MCQGenerater.html')
@app.route('/chatbot') 
def chatbot_page(): return render_template('Chatbot.html')
@app.route('/contact') 
def contact_page(): return render_template('Devcontact.html')
@app.route('/profile') 
def profile_page(): return render_template('Studentdashboard.html')
@app.route('/analytics') 
def analytics_page(): return render_template('analytics.html')

@app.route('/summarize', methods=['POST'])
def summarize():
    try:
        stream = request.form.get('stream','false').lower()=='true'
        file = request.files.get('file'); text = ''; doc_hash = request.form.get('doc_hash','').strip()
        if doc_hash: text = document_manager.get_document_text(doc_hash) or ''
        if not text:
            if request.form.get('text'): text = request.form['text']
            elif file and file.filename:
                file.filename = secure_filename(file.filename); text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])
        if not text or not text.strip() or text.startswith("Error:"): return jsonify({'error':'No text'}),400
        cur_hash = document_manager.store_document(text, filename=(file.filename if file and file.filename else None))
        if stream:
            @stream_with_context
            def gen():
                summary=''
                try:
                    for chunk in content_processor.generate_summary_stream(text):
                        yield chunk
                        if chunk.startswith("data: "):
                            d=json.loads(chunk[6:])
                            if d.get('type')=='chunk': summary+=d.get('content','')
                            elif d.get('type')=='done': summary=d.get('full_content',summary)
                except Exception:
                    logging.exception("stream err"); yield make_sse({'type':'error','content':'Summary failed'})
                yield make_sse({'type':'mcq_start'})
                try: mcqs = mcq_generator.generate_meaningful_mcqs(summary, num_questions=config.MAX_MCQS_TO_GENERATE)
                except: mcqs = []
                yield make_sse({'type':'mcq_done','mcqs':mcqs,'doc_hash':cur_hash,'filename': file.filename if file and file.filename else 'text_input'})
            return Response(gen(), headers=sse_headers())
        summary = content_processor.generate_bullet_point_summary(text)
        mcqs = mcq_generator.generate_meaningful_mcqs(summary, num_questions=config.MAX_MCQS_TO_GENERATE)
        return jsonify({'summary':summary,'mcqs':mcqs,'doc_hash':cur_hash,'filename': file.filename if file and file.filename else 'text_input'})
    except Exception:
        logging.exception("summarize"); return jsonify({'error':'Internal'}),500

@app.route('/ask-ai', methods=['POST'])
def ask_ai():
    try:
        q=request.form.get('question','').strip(); file=request.files.get('file'); doc_hash=request.form.get('doc_hash','').strip(); document_text=None
        if doc_hash: document_text = document_manager.get_document_text(doc_hash)
        if not document_text and file and file.filename:
            file.filename = secure_filename(file.filename); document_text = utils.extract_text_from_file(file, app.config['UPLOAD_FOLDER'])
            if not document_text.startswith("Error:"): doc_hash = document_manager.store_document(document_text, file.filename)
        if document_text and not document_text.startswith("Error:"): bot.setup_document(document_text)
        if not q: return jsonify({'answer':"Please ask a question or upload a document."})
        stream = request.form.get('stream','false').lower()=='true'
        if stream:
            @stream_with_context
            def gen():
                try:
                    use_doc = document_text is not None and getattr(bot,'qa_chain',None) is not None
                    for chunk in bot.answer_query_stream(q, use_document=use_doc): yield chunk
                except Exception:
                    logging.exception("chat stream"); yield make_sse({'type':'error','content':'Chat failed'})
                yield make_sse({'type':'metadata','doc_hash':doc_hash if doc_hash else None})
            return Response(gen(), headers=sse_headers())
        ans = bot.answer_query(q, use_document=(document_text is not None and getattr(bot,'qa_chain',None) is not None))
        return jsonify({'answer':ans,'doc_hash':doc_hash if doc_hash else None})
    except Exception:
        logging.exception("ask_ai"); return jsonify({'answer':'Internal error'}),500

@app.route('/grade', methods=['POST'])
def grade():
    try:
        data = request.get_json(force=True)
        if not data.get('answer','').strip(): return jsonify({'score':0,'feedback':'Please write an answer first.'})
        score,feedback = evaluator.evaluate_student_answer(data.get('answer',''), data.get('reference',''))
        return jsonify({'score':score,'feedback':feedback})
    except Exception:
        logging.exception("grade"); return jsonify({'error':'Internal'}),500

@app.route('/submit_mcqs', methods=['POST'])
def submit_mcqs():
    if students_collection is None: return jsonify({'error':'DB unavailable'}),503
    try:
        d=request.json; score=int(d.get('score',0)); total=int(d.get('total',0))
        if total<=0: return jsonify({'error':'Invalid total'}),400
        rec={'student':d.get('student','Anonymous'),'score':score,'total':total,'percentage':round((score/total)*100,2),'mcqs':d.get('mcqs',[]),'timestamp':datetime.utcnow()}
        students_collection.insert_one(rec); return jsonify({'message':'saved','data':rec})
    except Exception:
        logging.exception("submit"); return jsonify({'error':'Failed'}),500

@app.route('/get_analytics/<student>')
def get_analytics(student):
    if students_collection is None: return jsonify({'error':'DB unavailable'}),503
    try:
        recs=list(students_collection.find({'student':str(student)},{'_id':0}).sort('timestamp',-1).limit(100))
        for r in recs:
            if isinstance(r.get('timestamp'), datetime): r['timestamp']=r['timestamp'].isoformat()+'Z'
        return jsonify(recs)
    except Exception:
        logging.exception("analytics"); return jsonify({'error':'Failed'}),500

@app.route('/documents')
def list_documents():
    try: return jsonify({'documents':document_manager.list_documents(),'stats':document_manager.get_stats()})
    except Exception:
        logging.exception("docs"); return jsonify({'error':'Failed'}),500

@app.route('/documents/<doc_hash>')
def get_document_info(doc_hash):
    d=document_manager.get_document(doc_hash)
    if not d: return jsonify({'error':'Not found'}),404
    ts=d.get('timestamp'); ts=ts.isoformat()+'Z' if hasattr(ts,'isoformat') else ts
    preview=d.get('text','')[:200]+('...' if len(d.get('text',''))>200 else '')
    return jsonify({'hash':d.get('hash'),'filename':d.get('filename'),'size':d.get('size'),'timestamp':ts,'preview':preview})

@app.route('/healthz')
def healthz(): return jsonify({'ok': client is not None}), (200 if client is not None else 500)

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)), debug=False, threaded=True)