document.addEventListener('DOMContentLoaded', function() {

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
            let summaryResult = document.getElementById("summaryResult");
            const submitBtn = e.target.querySelector('button[type="submit"]');
            const originalBtnText = submitBtn ? submitBtn.textContent : '';
            
            summaryResult.innerHTML = "<p><em>Summarizing...</em></p>";
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Processing...";
            }
            
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 120000);
                
                let res = await fetch("/summarize", { 
                    method: "POST", 
                    body: formData,
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                
                if (!res.ok) throw new Error(`Server error: ${res.status}`);
                let data = await res.json();
                if(data.error) throw new Error(data.error);
                summaryResult.innerHTML = "<h3>Summary:</h3><div>" + data.summary.replace(/\n/g, '<br>') + "</div>";
            } catch (error) {
                if (error.name === 'AbortError') {
                    summaryResult.innerHTML = `<p style="color:red;">⚠️ Request timed out. Please try again.</p>`;
                } else {
                    summaryResult.innerHTML = `<p style="color:red;">⚠️ ${error.message}</p>`;
                }
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
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 180000);
                
                const res = await fetch('/ask-ai', { 
                    method: 'POST', 
                    body: formData,
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                
                if (!res.ok) throw new Error(`Server error: ${res.status}`);
                const data = await res.json();
                loadingMsg.remove();
                const aiMsgHtml = `<b>AI:</b> ${data.answer || 'Sorry, I could not find an answer.'}`;
                appendMessage(aiMsgHtml, 'ai');
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
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 120000);
                
                const res = await fetch("/summarize", { 
                    method: "POST", 
                    body: formData,
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                
                if (!res.ok) throw new Error("Server error: Failed to generate MCQs");
                const data = await res.json();
                loading.style.display = "none";

                if (!data.mcqs || data.mcqs.length === 0) {
                    resultDiv.innerHTML = "<p>No MCQs were generated. Please try again.</p>";
                    return;
                }

                let html = "<h3>Generated MCQs:</h3>";
                data.mcqs.forEach((mcq, idx) => {
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