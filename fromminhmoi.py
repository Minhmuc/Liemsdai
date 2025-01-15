from flask import Flask, render_template, request
import json
import re

app = Flask(__name__)

def parse_questions(data):
    result = []
    for idx, question in enumerate(data['data'][0]['test'], start=1):
        question_id = question['id']
        question_text = question['question_direction']
        answers = question['answer_option']

        question_cleaned = clean_html(question_text)
        answer_cleaned = {chr(65 + i): clean_html(answer['value']) for i, answer in enumerate(answers)}

        formatted_question = {
            "ID": question_id,
            "Câu": f"Câu {idx}: {question_cleaned}",
            "Đáp án": answer_cleaned
        }
        result.append(formatted_question)

    return result

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    cleantext = re.sub(r'&nbsp;|&amp;|&quot;|&lt;|&gt;', ' ', cleantext)
    return cleantext.strip()

@app.route('/', methods=['GET', 'POST'])
def index():
    questions = []
    if request.method == 'POST':
        file = request.files['file']
        if file:
            data = json.load(file)
            questions = parse_questions(data)
    return render_template('index.html', questions=questions)

if __name__ == "__main__":
    app.run(debug=True)