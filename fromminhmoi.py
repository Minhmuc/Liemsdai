import os
import json
import re
from flask import Flask, render_template, request

app = Flask(__name__)

def parse_questions(files, id_filter=None):
    result = {}
    idx = 1
    for file in files:
        if file:
            if file.filename.endswith('.txt'):
                # Đọc file txt
                content = file.read().decode('utf-8')
                data = json.loads(content)
            else:
                # Đọc file json
                data = json.load(file)
            for question in data['data'][0]['test']:
                question_id = question['id']
                if id_filter and question_id != id_filter:
                    continue
                question_text = question['question_direction']
                answers = question['answer_option']

                question_cleaned = clean_html(question_text)
                answer_cleaned = {chr(65 + i): clean_html(answer['value']) for i, answer in enumerate(answers)}

                formatted_question = {
                    "ID": question_id,
                    "Câu": f"Câu {idx}: {question_cleaned}",
                    "Đáp án": answer_cleaned
                }
                if question_id not in result:
                    result[question_id] = formatted_question
                idx += 1
    return list(result.values())

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    cleantext = re.sub(r'&nbsp;|&amp;|&quot;|&lt;|&gt;', ' ', cleantext)
    return cleantext.strip()

@app.route('/', methods=['GET', 'POST'])
def index():
    questions = {}
    idx = 1
    if request.method == 'POST':
        files = request.files.getlist('file')  # Lấy danh sách tệp được chọn
        id_filter = request.form.get('id')  # Lấy giá trị ID từ form
        for file in files:
            if file:
                if file.filename.endswith('.txt') or file.filename.endswith('.json'):
                    questions_file = parse_questions([file], id_filter)  # Thêm câu hỏi vào danh sách
                    for question in questions_file:
                        if question['ID'] not in questions:
                            question['Câu'] = f"Câu {idx}: {question['Câu'].split(': ')[1]}"
                            questions[question['ID']] = question
                            idx += 1
    return render_template('index.html', questions=list(questions.values()), total_questions=len(questions))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))  # Sử dụng PORT từ biến môi trường
    app.run(host='0.0.0.0', port=port)