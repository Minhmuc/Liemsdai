import os
import json
import re
from flask import Flask, render_template, request, jsonify, send_from_directory, abort, send_file, session, redirect, url_for, Response
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import io
import zipfile
from functools import wraps
from google_drive_manager import GoogleDriveManager
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

# Load environment variables from .env file
load_dotenv()

UPLOAD_FOLDER = 'uploaded'
DATA_FOLDER = 'Data'
METADATA_FOLDER = 'metadata'
HIDDEN_FILES_JSON = 'hidden_files.json'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)
if not os.path.exists(METADATA_FOLDER):
    os.makedirs(METADATA_FOLDER)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max

# ProxyFix: Trust X-Forwarded-* headers from Render proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Load secret key from environment variable (IMPORTANT: Set this in .env file)
app.secret_key = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-production')
if app.secret_key == 'default-dev-key-change-in-production':
    print("⚠️ WARNING: Using default secret key. Set SECRET_KEY in .env file!")

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', '').split(',')
ADMIN_EMAILS = [email.strip() for email in ADMIN_EMAILS if email.strip()]
SUPER_ADMIN_EMAIL = os.environ.get('SUPER_ADMIN_EMAIL', '').strip()

# Initialize OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

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

# Hidden files management functions
def load_hidden_files():
    """Load danh sách file ẩn từ JSON"""
    if os.path.exists(HIDDEN_FILES_JSON):
        try:
            with open(HIDDEN_FILES_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_hidden_files(hidden_list):
    """Lưu danh sách file ẩn vào JSON"""
    with open(HIDDEN_FILES_JSON, 'w', encoding='utf-8') as f:
        json.dump(hidden_list, f, ensure_ascii=False, indent=2)

def is_super_admin():
    """Kiểm tra xem user hiện tại có phải super admin không"""
    if not SUPER_ADMIN_EMAIL:
        return False
    admin_email = session.get('admin_email', '')
    return admin_email.lower() == SUPER_ADMIN_EMAIL.lower()

def is_admin():
    """Kiểm tra xem user có phải admin không"""
    admin_email = session.get('admin_email', '')
    return admin_email.lower() in [email.lower() for email in ADMIN_EMAILS]

def get_visible_files():
    """Lấy danh sách file mà user hiện tại được phép thấy"""
    if drive_manager:
        all_files = [f['name'] for f in drive_manager.list_files()]
    else:
        all_files = [f for f in os.listdir(DATA_FOLDER) if os.path.isfile(os.path.join(DATA_FOLDER, f))]
    
    # Nếu là super admin (minhmuc), thấy tất cả file
    if is_super_admin():
        return all_files
    
    # Nếu không phải super admin, loại bỏ các file bị ẩn
    hidden_files = load_hidden_files()
    visible_files = [f for f in all_files if f not in hidden_files]
    
    return visible_files

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

print(f"🔧 ADMIN_EMAILS: {', '.join(ADMIN_EMAILS)}")
print(f"🔧 SUPER_ADMIN_EMAIL: {SUPER_ADMIN_EMAIL}")

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
    
    def process_question(question, idx):
        """Process a single question based on its type"""
        question_id = question['id']
        if id_filter and question_id != id_filter:
            return None, idx
            
        question_type = question.get('question_type', 'radio')
        question_text = question['question_direction']
        
        # Kiểm tra xem câu hỏi có chứa hình ảnh hay không
        has_image = '<img' in question_text
        
        # Clean HTML nhưng giữ lại dấu gạch dưới cho câu điền từ
        question_cleaned = clean_html(question_text)
        if has_image:
            question_cleaned += " [hình ảnh]"
        
        formatted_question = {
            "ID": question_id,
            "Loại": question_type,
            "Câu": f"Câu {idx}: {question_cleaned}",
        }
        
        # Handle different question types
        if question_type == 'radio' or question_type == 'checkbox':
            # Multiple choice questions (single or multiple answers)
            answers = question.get('answer_option', [])
            if answers:
                answer_cleaned = {chr(65 + i): clean_html(answer['value']) for i, answer in enumerate(answers)}
                formatted_question["Đáp án"] = answer_cleaned
                if question_type == 'checkbox':
                    formatted_question["Loại"] = "checkbox (chọn nhiều)"
            
        elif question_type == 'group-radio':
            # True/False questions with parent-child structure
            group_id = question.get('group_id', 0)
            if group_id == 0:
                # This is the parent question
                formatted_question["Có các câu đúng/sai"] = True
            else:
                # This is a child question with Đúng/Sai options
                formatted_question["Parent_ID"] = group_id
                formatted_question["Là câu đúng/sai"] = True
                answers = question.get('answer_option', [])
                if answers:
                    answer_cleaned = {chr(65 + i): clean_html(answer['value']) for i, answer in enumerate(answers)}
                    formatted_question["Đáp án"] = answer_cleaned
            
        elif question_type == 'drag_drop':
            # Drag and drop questions (matching)
            group_id = question.get('group_id', 0)
            if group_id == 0:
                # This is the parent question with all options
                answers = question.get('answer_option', [])
                formatted_question["Các lựa chọn"] = [clean_html(answer['value']) for answer in answers]
                formatted_question["Có các câu ghép"] = True
            else:
                # This is a child question that needs to be matched
                formatted_question["Parent_ID"] = group_id
                formatted_question["Là câu ghép"] = True
                
        elif question_type == 'group-input':
            # Input questions (fill in the blank)
            group_id = question.get('group_id', 0)
            if group_id == 0:
                # This is the parent question - keep underscores
                formatted_question["Có các câu điền"] = True
            else:
                # This is a child question - this is the answer
                formatted_question["Parent_ID"] = group_id
                formatted_question["Là đáp án điền"] = True
                formatted_question["Đáp án"] = question_cleaned
                
        else:
            # Unknown question type
            formatted_question["Đáp án"] = f"Loại câu hỏi không xác định: {question_type}"
        
        return formatted_question, idx + 1
    
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
                            formatted_question, idx = process_question(question, idx)
                            if formatted_question and formatted_question['ID'] not in result:
                                result[formatted_question['ID']] = formatted_question
                                
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
                    formatted_question, idx = process_question(question, idx)
                    if formatted_question and formatted_question['ID'] not in result:
                        result[formatted_question['ID']] = formatted_question
                        
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

    # Đánh số lại chỉ các câu hỏi chính (không phải câu con)
    main_idx = 1
    for question in sorted_questions:
        # Chỉ đánh số câu hỏi chính, bỏ qua câu con
        if not question.get('Là câu ghép') and not question.get('Là đáp án điền'):
            question['Câu'] = f"Câu {main_idx}: {question['Câu'].split(': ', 1)[1]}"
            main_idx += 1
    
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
        if not session.get('admin_logged_in') or not is_admin():
            # Redirect to OAuth login
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin login page - Show login page with Google button
@app.route('/admin/login')
def admin_login():
    """Show login page with Google OAuth button"""
    error = request.args.get('error')
    error_message = None
    if error == 'access_denied':
        error_message = '🚫 Từ chối truy cập: Bạn là ai?'
    elif error == 'oauth_failed':
        error_message = '❌ Lỗi xác thực: Không thể kết nối với Google'
    return render_template('admin_login.html', error=error_message)

# Admin OAuth redirect
@app.route('/admin/oauth/login')
def admin_oauth_login():
    """Redirect to Google OAuth login"""
    # Dynamic redirect URI based on request
    redirect_uri = url_for('admin_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

# Admin OAuth callback
@app.route('/admin/callback')
def admin_callback():
    """Handle Google OAuth callback"""
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            return render_template('admin_login_error.html', 
                                 error='Không thể lấy thông tin người dùng từ Google')
        
        email = user_info.get('email')
        name = user_info.get('name')
        picture = user_info.get('picture')
        
        # Check if user is authorized admin
        if email.lower() not in [e.lower() for e in ADMIN_EMAILS]:
            return redirect(url_for('admin_login', error='access_denied'))
        
        # Set session
        session['admin_logged_in'] = True
        session['admin_email'] = email
        session['admin_name'] = name
        session['admin_picture'] = picture
        
        return redirect(url_for('admin'))
        
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return redirect(url_for('admin_login', error='oauth_failed'))

# Admin logout
@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

# Admin dashboard
@app.route('/admin')
@admin_required
def admin():
    admin_email = session.get('admin_email', '')
    admin_name = session.get('admin_name', 'Admin')
    admin_picture = session.get('admin_picture', '')
    
    # Get visible files based on user permission
    visible_files = get_visible_files()
    hidden_files = load_hidden_files() if is_super_admin() else []
    
    return render_template(
        'admin.html', 
        admin_name=admin_name,
        admin_email=admin_email,
        admin_picture=admin_picture,
        is_super_admin=is_super_admin(),
        hidden_files=hidden_files
    )

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
    admin_name = session.get('admin_name', 'Admin')
    uploader_name = admin_name
    
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
        visible_files = get_visible_files()
        hidden_files = load_hidden_files() if is_super_admin() else []
        
        files = []
        
        if drive_manager:
            # List from Google Drive
            drive_files = drive_manager.list_files()
            for file in drive_files:
                # Skip hidden files if not super admin
                if file['name'] not in visible_files and not is_super_admin():
                    continue
                
                # Get uploader from properties
                properties = file.get('properties', {})
                uploader = properties.get('uploader', 'Unknown')
                    
                files.append({
                    'name': file['name'],
                    'size': file.get('size', 0),
                    'modified': file.get('modifiedTime', ''),
                    'uploader': uploader,
                    'hidden': file['name'] in hidden_files
                })
        else:
            # List from local storage
            for filename in os.listdir(DATA_FOLDER):
                # Skip hidden files if not super admin
                if filename not in visible_files and not is_super_admin():
                    continue
                    
                filepath = os.path.join(DATA_FOLDER, filename)
                if os.path.isfile(filepath):
                    size = os.path.getsize(filepath)
                    modified = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                    metadata = get_file_metadata(filename)
                    files.append({
                        'name': filename,
                        'size': size,
                        'modified': modified,
                        'uploader': metadata['uploader'] if metadata else 'Unknown',
                        'hidden': filename in hidden_files
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

# Toggle file visibility (super admin only)
@app.route('/admin/toggle_visibility', methods=['POST'])
@admin_required
def toggle_file_visibility():
    """Toggle ẩn/hiện file - chỉ super admin (minhmuc) mới làm được"""
    if not is_super_admin():
        return jsonify({'success': False, 'error': 'Chỉ minhmuc mới có quyền ẩn/hiện file'}), 403
    
    data = request.get_json()
    filename = data.get('filename')
    
    if not filename:
        return jsonify({'success': False, 'error': 'Missing filename'}), 400
    
    hidden_files = load_hidden_files()
    
    if filename in hidden_files:
        # Bỏ ẩn file
        hidden_files.remove(filename)
        action = 'unhidden'
    else:
        # Ẩn file
        hidden_files.append(filename)
        action = 'hidden'
    
    save_hidden_files(hidden_files)
    
    return jsonify({
        'success': True,
        'action': action,
        'filename': filename,
        'hidden_files': hidden_files
    })

# Get hidden files list (super admin only)
@app.route('/admin/hidden_files', methods=['GET'])
@admin_required
def get_hidden_files_route():
    """Lấy danh sách file ẩn - chỉ super admin thấy được"""
    if not is_super_admin():
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    hidden_files = load_hidden_files()
    return jsonify({'success': True, 'hidden_files': hidden_files})

# SEO Routes
@app.route('/robots.txt')
def robots():
    """Serve robots.txt file"""
    return send_from_directory('.', 'robots.txt')

@app.route('/sitemap.xml')
def sitemap():
    """Generate dynamic sitemap.xml"""
    pages = []
    base_url = 'https://lms.liemsdai.is-best.net'
    
    # Main pages
    pages.append({
        'loc': f'{base_url}/',
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '1.0'
    })
    
    pages.append({
        'loc': f'{base_url}/casual',
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'weekly',
        'priority': '0.8'
    })
    
    pages.append({
        'loc': f'{base_url}/dev',
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'weekly',
        'priority': '0.8'
    })
    
    # Generate XML
    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    for page in pages:
        sitemap_xml += '  <url>\n'
        sitemap_xml += f'    <loc>{page["loc"]}</loc>\n'
        sitemap_xml += f'    <lastmod>{page["lastmod"]}</lastmod>\n'
        sitemap_xml += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        sitemap_xml += f'    <priority>{page["priority"]}</priority>\n'
        sitemap_xml += '  </url>\n'
    
    sitemap_xml += '</urlset>'
    
    return Response(sitemap_xml, mimetype='text/xml')

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
