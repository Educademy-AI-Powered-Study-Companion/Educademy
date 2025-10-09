// static/js/voice.js

function recordVoice(inputElement) {
  const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
  if (!recognition) {
    alert("Speech recognition is not supported in this browser.");
    return;
  }
  
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.start();
  
  // Provide feedback to the user that recording has started
  const originalPlaceholder = inputElement.placeholder;
  const voiceBtn = document.getElementById('voiceBtn');
  inputElement.placeholder = "Listening...";
  if (voiceBtn) voiceBtn.style.color = '#e74c3c'; // Change color to indicate recording

  recognition.onresult = (event) => {
    const speechResult = event.results[0][0].transcript;
    inputElement.value = speechResult;
  };

  recognition.onspeechend = () => {
    recognition.stop();
    inputElement.placeholder = originalPlaceholder;
    if (voiceBtn) voiceBtn.style.color = ''; // Reset color
  };

  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error);
    inputElement.placeholder = originalPlaceholder;
    if (voiceBtn) voiceBtn.style.color = ''; // Reset color
    if (event.error === 'no-speech') {
        alert("No speech was detected. Please try again.");
    }
  };
}