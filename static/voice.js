function recordVoice() {
  const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
  recognition.lang = 'en-IN';  // Use 'en-IN' for English
  recognition.start();

  recognition.onresult = function(event) {
    document.getElementById("inputText").value = event.results[0][0].transcript;
  };
}
