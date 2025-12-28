import os
import json
import re
from flask import Flask, render_template, request, jsonify, send_from_directory, abort, send_file, session, redirect, url_for
from datetime import datetime
import io
import zipfile
from functools import wraps
from google_drive_manager import GoogleDriveManager

UPLOAD_FOLDER = 'uploaded'
DATA_FOLDER = 'Data'
METADATA_FOLDER = 'metadata'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)
if not os.path.exists(METADATA_FOLDER):
    os.makedirs(METADATA_FOLDER)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.secret_key = 'liems-secret-key-2025'  # Change this to a random string

# Admin passwords - THAY ĐỔI MẬT KHẨU NÀY
ADMIN_PASSWORDS = ['c^ng', 'hoanbucon', 'minhmuc']

# Password to display name mapping
PASSWORD_NAMES = {
    'hoanbucon': 'Hoàn Bự Con',
    'c^ng': 'Ming King',
    'minhmuc': 'Strongest LiemDaiHiep'
}

# Google Drive setup
USE_GOOGLE_DRIVE = os.environ.get('USE_GOOGLE_DRIVE', 'false').lower() == 'true'
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', None)

# Metadata functions
def save_file_metadata(filename, uploader):
    """Save metadata about file upload"""
    metadata_file = os.path.join(METADATA_FOLDER, f"{filename}.json")
    metadata = {
        'filename': filename,
        'uploader': uploader,
        'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    try:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving metadata: {e}")

def get_file_metadata(filename):
    """Get metadata about file upload"""
    metadata_file = os.path.join(METADATA_FOLDER, f"{filename}.json")
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading metadata: {e}")
    return None

print(f"🔧 USE_GOOGLE_DRIVE: {USE_GOOGLE_DRIVE}")
print(f"🔧 DRIVE_FOLDER_ID: {DRIVE_FOLDER_ID}")

# Initialize Google Drive if enabled
drive_manager = None
if USE_GOOGLE_DRIVE:
    print("🚀 Initializing Google Drive...")
    try:
        if not os.path.exists('credentials.json'):
            print("❌ credentials.json not found!")
            drive_manager = None
        else:
            print("✅ credentials.json found")
            drive_manager = GoogleDriveManager(
                credentials_file='credentials.json',
                folder_id=DRIVE_FOLDER_ID
            )
            print(f"✅ Google Drive enabled with folder ID: {DRIVE_FOLDER_ID or 'ROOT'}")
    except Exception as e:
        print(f"❌ Google Drive initialization failed: {e}")
        import traceback
        traceback.print_exc()
        drive_manager = None
else:
    print("ℹ️ Google Drive disabled - using local storage")

def parse_questions(files=None, json_codes=None, id_filter=None):
    result = {}
    idx = 1
    errors = []
    
    def extract_questions_from_data(data):
        """Helper function to extract questions from different JSON structures"""
        # Cấu trúc mới: {'test': [...]}
        if 'test' in data and isinstance(data['test'], list):
            return data['test']
        # Cấu trúc cũ: {'data': [{'test': [...]}]}
        elif 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
            if 'test' in data['data'][0]:
                return data['data'][0]['test']
        return []
    
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
                        
                        questions = extract_questions_from_data(data)
                        if not questions:
                            errors.append(f"File {file.filename} không chứa câu hỏi hợp lệ")
                            continue
                        
                        for question in questions:
                            question_id = question['id']
                            if id_filter and question_id != id_filter:
                                continue
                            question_text = question['question_direction']
                            answers = question['answer_option']

                            question_cleaned = clean_html(question_text)
                            answer_cleaned = {chr(65 + i): clean_html(answer['value']) for i, answer in enumerate(answers)}

                            # Kiểm tra xem câu hỏi có chứa hình ảnh hay không
                            if '<img' in question_text:
                                question_cleaned += " [hình ảnh]"

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
                
                questions = extract_questions_from_data(data)
                if not questions:
                    errors.append(f"JSON code không chứa câu hỏi hợp lệ")
                    continue
                
                for question in questions:
                    question_id = question['id']
                    if id_filter and question_id != id_filter:
                        continue
                    question_text = question['question_direction']
                    answers = question['answer_option']

                    question_cleaned = clean_html(question_text)
                    answer_cleaned = {chr(65 + i): clean_html(answer['value']) for i, answer in enumerate(answers)}

                    # Kiểm tra xem câu hỏi có chứa hình ảnh hay không
                    if '<img' in question_text:
                        question_cleaned += " [hình ảnh]"

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
    response = render_template('index.html')
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

@app.route('/static/<path:filename>')
def static_files(filename):
    return app.send_static_file(filename)

@app.route('/ping')
def ping():
    return "pong", 200

@app.route('/test-drive')
def test_drive():
    """Endpoint to test Google Drive connection"""
    result = {
        'use_google_drive': USE_GOOGLE_DRIVE,
        'folder_id': DRIVE_FOLDER_ID,
        'drive_manager_initialized': drive_manager is not None,
        'credentials_exists': os.path.exists('credentials.json')
    }
    
    if drive_manager:
        try:
            files = drive_manager.list_files()
            result['drive_connected'] = True
            result['files_count'] = len(files)
            result['files'] = [f['name'] for f in files[:5]]  # First 5 files
        except Exception as e:
            result['drive_connected'] = False
            result['error'] = str(e)
    
    return jsonify(result)

import os
from flask import send_from_directory, abort

@app.route('/casual')
def casual():
    return render_template('casual.html')

@app.route('/redirect-to-ad')
def redirect_to_ad():
    filename = request.args.get('file')
    if not filename:
        abort(400, description="Filename required")
    
    # Build callback URL
    callback_url = request.url_root + 'casual?autodownload=true&file=' + filename
    
    # Create Shrinkme redirect URL
    shrinkme_api_key = '4aa2dedcdc780d528a0512535ac3fcd7b594743b'
    shrinkme_url = f'https://shrinkme.io/st?api={shrinkme_api_key}&url={callback_url}'
    
    # Render redirect page
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0;url={shrinkme_url}">
    <title>Redirecting...</title>
</head>
<body>
    <p>Đang chuyển hướng đến trang quảng cáo...</p>
    <p>Nếu không tự động chuyển, <a href="{shrinkme_url}">nhấn vào đây</a></p>
</body>
</html>'''

@app.route('/api/data-files')
def data_files():
    try:
        if drive_manager:
            # List from Google Drive
            drive_files = drive_manager.list_files()
            files = [f['name'] for f in drive_files]
        else:
            # List from local storage
            files = os.listdir(DATA_FOLDER)
            files = [f for f in files if os.path.isfile(os.path.join(DATA_FOLDER, f))]
        
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/data/<path:filename>')
def download_data_file(filename):
    # Security check: prevent path traversal attacks
    if '..' in filename or filename.startswith('/'):
        abort(400, description="Invalid filename")
    
    try:
        if drive_manager:
            # Download from Google Drive to temp location
            import tempfile
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, filename)
            
            success = drive_manager.download_file_by_name(filename, temp_path)
            
            if success and os.path.exists(temp_path):
                response = send_file(temp_path, as_attachment=True, download_name=filename)
                # Clean up temp file after sending
                try:
                    os.remove(temp_path)
                except:
                    pass
                return response
            else:
                abort(404, description="File not found on Drive")
        else:
            # Download from local storage
            return send_from_directory(DATA_FOLDER, filename, as_attachment=True)
    
    except FileNotFoundError:
        abort(404, description="File not found")
    except Exception as e:
        abort(500, description=str(e))

@app.route('/download/data-multiple', methods=['POST'])
def download_multiple_files():
    data_folder = 'Data'
    files = request.json.get('files', [])
    if not files:
        return jsonify({'error': 'No files selected'}), 400

    # Security check: prevent path traversal attacks
    for filename in files:
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': 'Invalid filename detected'}), 400

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename in files:
            file_path = os.path.join(data_folder, filename)
            if os.path.isfile(file_path):
                zf.write(file_path, arcname=filename)
            else:
                return jsonify({'error': f'File not found: {filename}'}), 404
    memory_file.seek(0)
    return send_file(memory_file, attachment_filename='selected_files.zip', as_attachment=True)

@app.route('/dev', methods=['GET', 'POST'])
def dev():
    questions = {}
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

    # Sắp xếp các câu hỏi theo ID
    sorted_questions = sorted(questions.values(), key=lambda x: x['ID'])

    # Đánh số lại các câu hỏi theo thứ tự
    for idx, question in enumerate(sorted_questions, start=1):
        question['Câu'] = f"Câu {idx}: {question['Câu'].split(': ', 1)[1]}"
    
    # Xóa tất cả các tệp trong thư mục uploaded
    for filename in os.listdir(UPLOAD_FOLDER):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
    total_questions = len(sorted_questions)
    return render_template('Dev.html', questions=sorted_questions, errors=errors, total_questions=total_questions)

# Admin authentication decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin login page
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        # Normalize password to lowercase for case-insensitive comparison
        if password and password.lower() in [p.lower() for p in ADMIN_PASSWORDS]:
            session['admin_logged_in'] = True
            # Store the original password (lowercase) to identify user
            for admin_pwd in ADMIN_PASSWORDS:
                if password.lower() == admin_pwd.lower():
                    session['admin_user'] = admin_pwd
                    break
            return redirect(url_for('admin'))
        else:
            return render_template('admin_login.html', error='Từ Chối Truy Cập!')
    return render_template('admin_login.html')

# Admin logout
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_user', None)
    return redirect(url_for('admin_login'))

# Admin dashboard
@app.route('/admin')
@admin_required
def admin():
    admin_user = session.get('admin_user', '')
    display_name = PASSWORD_NAMES.get(admin_user, 'Admin')
    return render_template('admin.html', admin_name=display_name)

# Admin upload file
@app.route('/admin/upload', methods=['POST'])
@admin_required
def admin_upload():
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    uploaded_files = []
    errors = []
    
    # Get uploader info
    admin_user = session.get('admin_user', '')
    uploader_name = PASSWORD_NAMES.get(admin_user, 'Admin')
    
    for file in files:
        if file and file.filename:
            try:
                if drive_manager:
                    # Upload to Google Drive with uploader info
                    file_id = drive_manager.upload_file_object(file, file.filename, uploader_name)
                    if file_id:
                        uploaded_files.append(file.filename)
                    else:
                        errors.append(f"{file.filename}: Failed to upload to Drive")
                else:
                    # Upload to local storage
                    filepath = os.path.join(DATA_FOLDER, file.filename)
                    file.save(filepath)
                    uploaded_files.append(file.filename)
                    # Save metadata for local files
                    save_file_metadata(file.filename, uploader_name)
            except Exception as e:
                errors.append(f"{file.filename}: {str(e)}")
    
    return jsonify({
        'success': len(uploaded_files),
        'uploaded': uploaded_files,
        'errors': errors
    })

# Admin list files
@app.route('/admin/files')
@admin_required
def admin_files():
    try:
        files = []
        
        if drive_manager:
            # List from Google Drive
            drive_files = drive_manager.list_files()
            for file in drive_files:
                properties = file.get('properties', {})
                files.append({
                    'name': file['name'],
                    'size': int(file.get('size', 0)),
                    'modified': file.get('modifiedTime', 'Unknown'),
                    'uploader': properties.get('uploader', 'Unknown')
                })
        else:
            # List from local storage
            for filename in os.listdir(DATA_FOLDER):
                filepath = os.path.join(DATA_FOLDER, filename)
                if os.path.isfile(filepath):
                    size = os.path.getsize(filepath)
                    modified = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                    metadata = get_file_metadata(filename)
                    files.append({
                        'name': filename,
                        'size': size,
                        'modified': modified,
                        'uploader': metadata['uploader'] if metadata else 'Unknown'
                    })
        
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin delete file
@app.route('/admin/delete/<filename>', methods=['DELETE'])
@admin_required
def admin_delete(filename):
    try:
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': 'Invalid filename'}), 400
        
        if drive_manager:
            # Delete from Google Drive
            success = drive_manager.delete_file_by_name(filename)
            if success:
                return jsonify({'success': True, 'message': f'Deleted {filename}'})
            else:
                return jsonify({'error': 'File not found or delete failed'}), 404
        else:
            # Delete from local storage
            filepath = os.path.join(DATA_FOLDER, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
                return jsonify({'success': True, 'message': f'Deleted {filename}'})
            else:
                return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin download multiple files as zip
@app.route('/admin/download-multiple', methods=['POST'])
@admin_required
def admin_download_multiple():
    try:
        data = request.get_json()
        filenames = data.get('files', [])
        
        if not filenames:
            return jsonify({'error': 'No files specified'}), 400
        
        # Create zip file in memory
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename in filenames:
                if '..' in filename or filename.startswith('/'):
                    continue
                
                try:
                    if drive_manager:
                        # Download from Google Drive
                        file_id = drive_manager.get_file_id_by_name(filename)
                        if file_id:
                            file_content = drive_manager.download_file_to_memory(file_id)
                            if file_content:
                                zf.writestr(filename, file_content)
                    else:
                        # Read from local storage
                        filepath = os.path.join(DATA_FOLDER, filename)
                        if os.path.isfile(filepath):
                            zf.write(filepath, filename)
                except Exception as e:
                    print(f"Error adding {filename} to zip: {e}")
                    continue
        
        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'files_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
