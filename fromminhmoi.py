import os
import json
import re
from flask import Flask, render_template, request, jsonify
from datetime import datetime

UPLOAD_FOLDER = 'uploaded'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app = Flask(__name__)

def parse_questions(files=None, json_codes=None, id_filter=None):
    result = {}
    idx = 1
    errors = []
    if files:
        for file in files:
            if file:
                if file.filename.endswith('.txt') or file.filename.endswith('.json'):
                    try:
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
                    except json.JSONDecodeError as e:
                        errors.append(f"File {file.filename} không đúng định dạng JSON: {e}")
                    except KeyError as e:
                        errors.append(f"File {file.filename} không đúng định dạng: {e}")
                    except Exception as e:
                        errors.append(f"File {file.filename} có lỗi: {e}")
                else:
                    errors.append(f"File {file.filename} không phải là file txt hoặc json")
    if json_codes:
        for json_code in json_codes:
            try:
                data = json.loads(json_code)
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
            except json.JSONDecodeError as e:
                errors.append(f"JSON code không đúng định dạng: {e}")
            except KeyError as e:
                errors.append(f"JSON code không đúng định dạng: {e}")
            except Exception as e:
                errors.append(f"JSON code có lỗi: {e}")
    return list(result.values()), errors

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    cleantext = re.sub(r'&nbsp;|&amp;|&quot;|&lt;|&gt;', ' ', cleantext)
    return cleantext.strip()

@app.route('/', methods=['GET', 'POST'])
def index():
    questions = {}
    idx = 1
    errors = []
    if request.method == 'POST':
        files = request.files.getlist('file')  # Lấy danh sách tệp được chọn
        json_code = request.form.get('json_code')  # Lấy JSON code từ form
        id_filter = request.form.get('id')  # Lấy giá trị ID từ form
        if files:
            questions_file, errors_file = parse_questions(files=files, id_filter=id_filter)  # Thêm câu hỏi vào danh sách
            questions.update({q['ID']: q for q in questions_file})
            errors.extend(errors_file)
        if json_code:
            questions_code, errors_code = parse_questions(json_codes=[json_code], id_filter=id_filter)  # Thêm câu hỏi từ JSON code
            questions.update({q['ID']: q for q in questions_code})
            errors.extend(errors_code)
    response = render_template('index.html', questions=list(questions.values()), total_questions=len(questions), errors=errors)
    # Xóa tất cả các tệp trong thư mục uploaded
    for filename in os.listdir(UPLOAD_FOLDER):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
    return response

@app.route('/save_json_code', methods=['POST'])
def save_json_code():
    data = request.get_json()
    json_code = data.get('json_code')
    if json_code:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        filename = f'uploaded_json_code_{timestamp}.txt'
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_code)
        return jsonify(success=True, filename=filepath)
    return jsonify(success=False)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))  # Sử dụng PORT từ biến môi trường
    app.run(host='0.0.0.0', port=port)