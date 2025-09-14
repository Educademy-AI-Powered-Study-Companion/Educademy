def generate_mcqs(summary_text):
    lines = summary_text.split('.')
    mcqs = []
    for i, line in enumerate(lines[:3]):
        mcqs.append({
            'question': f"What does this line mean? → {line.strip()}",
            'options': ['Option A', 'Option B', 'Option C', 'Option D'],
            'answer': 'Option A'
        })
    return mcqs
