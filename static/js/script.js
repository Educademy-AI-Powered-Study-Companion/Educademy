document.addEventListener('DOMContentLoaded', function() {
    
    function showCurrentDocument() {
        const docHash = sessionStorage.getItem('current_doc_hash');
        const docFilename = sessionStorage.getItem('current_doc_filename');
        
        if (docHash && docFilename) {
            let statusDiv = document.getElementById('documentStatus');
            if (!statusDiv) {
                statusDiv = document.createElement('div');
                statusDiv.id = 'documentStatus';
                statusDiv.style.cssText = 'position:fixed;top:80px;right:20px;background:#e8f4f8;padding:10px 15px;border-radius:8px;border:1px solid #2d7be5;z-index:1000;max-width:300px;font-size:0.85em;box-shadow:0 2px 8px rgba(0,0,0,0.1);';
                document.body.appendChild(statusDiv);
            }
            statusDiv.innerHTML = `
                <strong style="color:#2d7be5;">📄 Active Document:</strong><br>
                ${docFilename}<br>
                <small style="color:#666;">Hash: ${docHash.substring(0, 8)}...</small><br>
                <button onclick="sessionStorage.removeItem('current_doc_hash'); sessionStorage.removeItem('current_doc_filename'); location.reload();" 
                        style="margin-top:5px;padding:3px 8px;background:#dc3545;color:white;border:none;border-radius:4px;cursor:pointer;font-size:0.8em;">
                    Clear
                </button>
            `;
        } else {
            const statusDiv = document.getElementById('documentStatus');
            if (statusDiv) statusDiv.remove();
        }
    }
    
    showCurrentDocument();
    
    const originalSetItem = sessionStorage.setItem;
    sessionStorage.setItem = function(key, value) {
        originalSetItem.call(this, key, value);
        if (key === 'current_doc_hash' || key === 'current_doc_filename') {
            setTimeout(showCurrentDocument, 100);
        }
    };

    const authModal = document.getElementById('authModal');
    if (authModal) {

        const preloader = document.getElementById("preloader");
        if(preloader) {
            window.addEventListener("load", () => {
                preloader.classList.add("hidden");
            });
        }

        window.openModal = function() { authModal.style.display = "flex"; }
        window.closeModal = function() { authModal.style.display = "none"; }
        window.toggleForms = function() {
            const signIn = document.getElementById("signInForm");
            const signUp = document.getElementById("signUpForm");
            if (signIn.style.display === "none") {
                signIn.style.display = "block";
                signUp.style.display = "none";
            } else {
                signIn.style.display = "none";
                signUp.style.display = "block";
            }
        }
        window.onclick = function(e) {
            if (e.target === authModal) {
                closeModal();
            }
        };
    }


    const summaryForm = document.getElementById('summaryForm');
    if (summaryForm) {
        let isProcessing = false;
        summaryForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (isProcessing) return;
            isProcessing = true;
            
            let formData = new FormData(e.target);
            formData.append('stream', 'true');
            let summaryResult = document.getElementById("summaryResult");
            const submitBtn = e.target.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn ? submitBtn.textContent : '';
            
            summaryResult.innerHTML = "<h3>Summary:</h3><div id='summaryContent' style='min-height:50px;'><em>Generating summary...</em></div>";
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Processing...";
            }
            
            try {
                const response = await fetch("/summarize", { 
                    method: "POST", 
                    body: formData
                });
                
                if (!response.ok) throw new Error(`Server error: ${response.status}`);
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let summaryContent = "";
                let mcqs = null;
                let docHash = null;
                let filename = null;
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                
                                if (data.type === 'start') {
                                    summaryContent = "";
                                    document.getElementById('summaryContent').innerHTML = "";
                                } else if (data.type === 'chunk') {
                                    summaryContent += data.content;
                                    const contentDiv = document.getElementById('summaryContent');
                                    if (contentDiv) {
                                        contentDiv.innerHTML = summaryContent.replace(/\n/g, '<br>');
                                        contentDiv.scrollTop = contentDiv.scrollHeight;
                                    }
                                } else if (data.type === 'done') {
                                    summaryContent = data.full_content || summaryContent;
                                    document.getElementById('summaryContent').innerHTML = summaryContent.replace(/\n/g, '<br>');
                                } else if (data.type === 'mcq_start') {
                                    document.getElementById('summaryContent').innerHTML += '<br><br><em>Generating MCQs...</em>';
                                } else if (data.type === 'mcq_done') {
                                    mcqs = data.mcqs;
                                    docHash = data.doc_hash;
                                    filename = data.filename;
                                    
                                    if (docHash) {
                                        sessionStorage.setItem('current_doc_hash', docHash);
                                        sessionStorage.setItem('current_doc_filename', filename || 'text_input');
                                    }
                                    
                                    if (mcqs && mcqs.length > 0) {
                                        let mcqHtml = "<h3>Generated MCQs:</h3>";
                                        mcqs.forEach((mcq, idx) => {
                                            const escapedAnswer = mcq.answer.replace(/"/g, '&quot;');
                                            const escapedQuestion = mcq.question.replace(/"/g, '&quot;');
                                            mcqHtml += `
                                                <div class="mcq-block" data-answer="${escapedAnswer}">
                                                    <p><b>Q${idx + 1}:</b> ${escapedQuestion}</p>
                                                    <fieldset>
                                                        ${mcq.options.map(opt => {
                                                            const escapedOpt = opt.replace(/"/g, '&quot;');
                                                            return `<label><input type="radio" name="q${idx}" value="${escapedOpt}"> ${opt}</label><br>`;
                                                        }).join('')}
                                                    </fieldset>
                                                </div>`;
                                        });
                                        mcqHtml += `<button type="button" id="submitQuizBtn">Submit Quiz</button>`;
                                        summaryResult.innerHTML += mcqHtml;
                                        document.getElementById("submitQuizBtn").addEventListener("click", checkAnswers);
                                    }
                                    
                                    if (docHash) {
                                        summaryResult.innerHTML += `<p style="margin-top:10px; color:#666; font-size:0.9em;">
                                            <strong>Document saved:</strong> ${filename || 'text_input'} 
                                            (Hash: ${docHash.substring(0, 8)}...)
                                            <br><small>You can now use this document in other features (MCQ, Chatbot) without re-uploading.</small>
                                        </p>`;
                                    }
                                } else if (data.type === 'error') {
                                    throw new Error(data.content);
                                }
                            } catch (parseError) {
                                console.error('Error parsing SSE data:', parseError);
                            }
                        }
                    }
                }
            } catch (error) {
                summaryResult.innerHTML = `<p style="color:red;">⚠️ ${error.message}</p>`;
            } finally {
                isProcessing = false;
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalBtnText;
                }
            }
        });
    }
    const chatForm = document.getElementById('chatForm');
    if (chatForm) {
        const userInput = document.getElementById('userInput');
        const fileInput = document.getElementById('fileInput');
        const chatArea = document.getElementById('chatArea');
        let isProcessing = false;

        chatForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            if (isProcessing) return;
            
            const question = userInput.value.trim();
            const file = fileInput.files[0];
            if (!question && !file) return;

            isProcessing = true;
            const submitBtn = chatForm.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.disabled = true;

            const userMsgHtml = `<b>You:</b> ${question || "(Uploaded: " + file.name + ")"}`;
            appendMessage(userMsgHtml, 'user');
            
            const loadingMsg = appendMessage('AI is thinking...', 'loading');
            chatArea.scrollTop = chatArea.scrollHeight;

            const formData = new FormData();
            if (question) formData.append("question", question);
            if (file) formData.append("file", file);

            try {
                const storedDocHash = sessionStorage.getItem('current_doc_hash');
                if (storedDocHash && !file) {
                    formData.append('doc_hash', storedDocHash);
                }
                formData.append('stream', 'true');
                
                const response = await fetch('/ask-ai', { 
                    method: 'POST', 
                    body: formData
                });
                
                if (!response.ok) throw new Error(`Server error: ${response.status}`);
                
                loadingMsg.remove();
                const streamingMsg = appendMessage('<b>AI:</b> <span id="aiResponseContent"></span>', 'ai');
                const responseContent = streamingMsg.querySelector('#aiResponseContent');
                let fullResponse = "";
                let docHash = null;
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                
                                if (data.type === 'start') {
                                    fullResponse = "";
                                    if (responseContent) responseContent.textContent = "";
                                } else if (data.type === 'chunk') {
                                    fullResponse += data.content;
                                    if (responseContent) {
                                        responseContent.textContent = fullResponse;
                                        chatArea.scrollTop = chatArea.scrollHeight;
                                    }
                                } else if (data.type === 'done') {
                                    fullResponse = data.full_content || fullResponse;
                                    if (responseContent) responseContent.textContent = fullResponse;
                                } else if (data.type === 'metadata') {
                                    docHash = data.doc_hash;
                                    if (docHash) {
                                        sessionStorage.setItem('current_doc_hash', docHash);
                                    }
                                } else if (data.type === 'error') {
                                    throw new Error(data.content);
                                }
                            } catch (parseError) {
                                console.error('Error parsing SSE data:', parseError);
                            }
                        }
                    }
                }
                
                if (docHash && file) {
                    const metaDiv = document.createElement('small');
                    metaDiv.style.cssText = 'color:#666; display:block; margin-top:5px;';
                    metaDiv.textContent = `Document saved for reuse (Hash: ${docHash.substring(0, 8)}...)`;
                    streamingMsg.appendChild(metaDiv);
                } else if (storedDocHash && !file) {
                    const metaDiv = document.createElement('small');
                    metaDiv.style.cssText = 'color:#666; display:block; margin-top:5px;';
                    metaDiv.textContent = 'Using previously uploaded document';
                    streamingMsg.appendChild(metaDiv);
                }
                
                chatArea.scrollTop = chatArea.scrollHeight;
            } catch (err) {
                loadingMsg.innerHTML = `<b>AI:</b> ${err.name === 'AbortError' ? 'Request timed out. Please try again.' : 'Error getting response.'}`;
            } finally {
                isProcessing = false;
                if (submitBtn) submitBtn.disabled = false;
                userInput.value = '';
                fileInput.value = '';
                chatArea.scrollTop = chatArea.scrollHeight;
            }
        });

        function appendMessage(innerHTML, type) {
            const msgDiv = document.createElement('div');
            msgDiv.style.margin = '0.5em 0';
            if (type === 'loading') msgDiv.style.color = '#2d7be5';
            msgDiv.innerHTML = innerHTML;
            chatArea.appendChild(msgDiv);
            return msgDiv;
        }
    }

    const mcqForm = document.getElementById("mcqForm");
    if (mcqForm) {
        const resultDiv = document.getElementById("mcqResult");
        const scoreDiv = document.getElementById("quizScore");
        const loading = document.getElementById("loading");
        let isProcessing = false;

        mcqForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (isProcessing) return;
            isProcessing = true;
            
            resultDiv.innerHTML = "";
            scoreDiv.innerHTML = "";
            loading.style.display = "block";
            const submitBtn = mcqForm.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn ? submitBtn.textContent : '';
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Generating...";
            }

            try {
                const formData = new FormData(mcqForm);
                formData.append('stream', 'true');
                
                const storedDocHash = sessionStorage.getItem('current_doc_hash');
                if (storedDocHash && !formData.get('file') && !formData.get('text')) {
                    formData.append('doc_hash', storedDocHash);
                }
                
                const response = await fetch("/summarize", { 
                    method: "POST", 
                    body: formData
                });
                
                if (!response.ok) throw new Error("Server error: Failed to generate MCQs");
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let summaryText = "";
                let mcqs = null;
                let docHash = null;
                let filename = null;
                
                loading.innerHTML = "Generating summary and MCQs...";
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                
                                if (data.type === 'chunk') {
                                    summaryText += data.content;
                                } else if (data.type === 'done') {
                                    summaryText = data.full_content || summaryText;
                                } else if (data.type === 'mcq_start') {
                                    loading.innerHTML = "Summary complete. Generating MCQs...";
                                } else if (data.type === 'mcq_done') {
                                    mcqs = data.mcqs;
                                    docHash = data.doc_hash;
                                    filename = data.filename;
                                    
                                    if (docHash) {
                                        sessionStorage.setItem('current_doc_hash', docHash);
                                        sessionStorage.setItem('current_doc_filename', filename || 'text_input');
                                    }
                                } else if (data.type === 'error') {
                                    throw new Error(data.content);
                                }
                            } catch (parseError) {
                                console.error('Error parsing SSE data:', parseError);
                            }
                        }
                    }
                }
                
                loading.style.display = "none";

                if (!mcqs || mcqs.length === 0) {
                    resultDiv.innerHTML = "<p>No MCQs were generated. Please try again.</p>";
                    return;
                }

                let html = "<h3>Generated MCQs:</h3>";
                mcqs.forEach((mcq, idx) => {
                    const escapedAnswer = mcq.answer.replace(/"/g, '&quot;');
                    const escapedQuestion = mcq.question.replace(/"/g, '&quot;');
                    html += `
                        <div class="mcq-block" data-answer="${escapedAnswer}">
                            <p><b>Q${idx + 1}:</b> ${escapedQuestion}</p>
                            <fieldset>
                                ${mcq.options.map(opt => {
                                    const escapedOpt = opt.replace(/"/g, '&quot;');
                                    return `<label><input type="radio" name="q${idx}" value="${escapedOpt}"> ${opt}</label><br>`;
                                }).join('')}
                            </fieldset>
                        </div>`;
                });
                html += `<button type="button" id="submitQuizBtn">Submit Quiz</button>`;
                resultDiv.innerHTML = html;
                document.getElementById("submitQuizBtn").addEventListener("click", checkAnswers);

            } catch (error) {
                loading.style.display = "none";
                const errorMsg = error.name === 'AbortError' ? 'Request timed out. Please try again.' : error.message;
                resultDiv.innerHTML = `<p style="color:red;">⚠️ ${errorMsg}</p>`;
            } finally {
                isProcessing = false;
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalBtnText;
                }
            }
        });

        function checkAnswers() {
            const allQuestions = document.querySelectorAll('.mcq-block');
            let score = 0;
            allQuestions.forEach(questionBlock => {
                const correctAnswer = questionBlock.dataset.answer;
                const selectedRadio = questionBlock.querySelector('input[type="radio"]:checked');
                questionBlock.style.border = '1px solid #ddd'; 
                if (selectedRadio) {
                    if (selectedRadio.value === correctAnswer) {
                        score++;
                        questionBlock.style.border = '2px solid #28a745';
                    } else {
                        questionBlock.style.border = '2px solid #dc3545';
                    }
                } else {
                    questionBlock.style.border = '2px solid #ffc107';
                }
            });
            scoreDiv.innerHTML = `<h3>Your Score: ${score} out of ${allQuestions.length}</h3>`;
            scoreDiv.scrollIntoView({ behavior: 'smooth' });
        }
    }


    const avatarImg = document.getElementById('avatarImg');
    if (avatarImg) {

        const avatarInput = document.getElementById('avatarInput');
        avatarInput.addEventListener('change', (e) => {
            const f = e.target.files && e.target.files[0];
            if (!f) return;
            if (!f.type.startsWith('image/')) {
                alert('Please upload an image file.');
                return;
            }
            const reader = new FileReader();
            reader.onload = () => { avatarImg.src = reader.result; };
            reader.readAsDataURL(f);
        });
        
        document.querySelector('.avatar-edit').addEventListener('click', () => avatarInput.click());

        const ctx = document.getElementById('progressChart').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Completed', 'In Progress', 'Not Started'],
                datasets: [{
                    data: [65, 20, 15],
                    backgroundColor: ['#2ecc71', '#f39c12', '#95a5a6'],
                    hoverOffset: 6,
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
            }
        });
    }
});