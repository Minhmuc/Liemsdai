import os
import json
import re
from functools import wraps
from io import BytesIO
from fastapi import FastAPI, File, Form, Request, UploadFile, Body, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import inspect
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
import io
import zipfile
from google_drive_manager import GoogleDriveManager
from dotenv import load_dotenv
from authlib.integrations.starlette_client import OAuth

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

app = FastAPI()
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts='*')

# Load secret key from environment variable (IMPORTANT: Set this in .env file)
secret_key = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-production')
app.add_middleware(SessionMiddleware, secret_key=secret_key, max_age=60 * 60 * 24 * 7)
templates = Jinja2Templates(directory='templates')
app.mount('/static', StaticFiles(directory='static'), name='static')

if secret_key == 'default-dev-key-change-in-production':
    print("⚠️ WARNING: Using default secret key. Set SECRET_KEY in .env file!")

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', '').split(',')
ADMIN_EMAILS = [email.strip() for email in ADMIN_EMAILS if email.strip()]
SUPER_ADMIN_EMAIL = os.environ.get('SUPER_ADMIN_EMAIL', '').strip()

# Initialize OAuth
oauth = OAuth()
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

def is_super_admin(request: Request):
    """Kiểm tra xem user hiện tại có phải super admin không"""
    if not SUPER_ADMIN_EMAIL:
        return False
    admin_email = request.session.get('admin_email', '')
    return admin_email.lower() == SUPER_ADMIN_EMAIL.lower()

def is_admin(request: Request):
    """Kiểm tra xem user có phải admin không"""
    admin_email = request.session.get('admin_email', '')
    return admin_email.lower() in [email.lower() for email in ADMIN_EMAILS]

def get_visible_files(request: Request):
    """Lấy danh sách file mà user hiện tại được phép thấy"""
    if drive_manager:
        all_files = [f['name'] for f in drive_manager.list_files()]
    else:
        all_files = [f for f in os.listdir(DATA_FOLDER) if os.path.isfile(os.path.join(DATA_FOLDER, f))]
    
    # Nếu là super admin (minhmuc), thấy tất cả file
    if is_super_admin(request):
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

@app.api_route('/', methods=['GET', 'POST'])
def index(request: Request):
    response = templates.TemplateResponse(request=request, name='index.html')
    # Xóa tất cả các tệp trong thư mục uploaded
    for filename in os.listdir(UPLOAD_FOLDER):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)
    return response
@app.post('/save_json_code')
async def save_json_code(data: dict = Body(...)):
    json_code = data.get('json_code')
    if json_code:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        filename = f'uploaded_json_code_{timestamp}.txt'
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_code)
        return JSONResponse({'success': True, 'filename': filepath})
    return JSONResponse({'success': False})

@app.get('/ping')
def ping():
    return Response(content="pong", status_code=200)

@app.get('/test-drive')
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
    
    return JSONResponse(result)

@app.get('/casual')
def casual(request: Request):
    return templates.TemplateResponse(request=request, name='casual.html')

@app.get('/redirect-to-ad')
def redirect_to_ad(request: Request):
    filename = request.query_params.get('file')
    if not filename:
        raise HTTPException(status_code=400, detail="Filename required")
    
    # Build callback URL
    callback_url = str(request.url_for('casual')) + '?autodownload=true&file=' + filename
    
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

@app.get('/api/data-files')
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
        
        return JSONResponse(files)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)

@app.get('/download/data/{filename:path}')
def download_data_file(filename):
    # Security check: prevent path traversal attacks
    if '..' in filename or filename.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    try:
        if drive_manager:
            # Download from Google Drive to temp location
            import tempfile
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, filename)
            
            success = drive_manager.download_file_by_name(filename, temp_path)
            
            if success and os.path.exists(temp_path):
                response = FileResponse(temp_path, filename=filename)
                # Clean up temp file after sending
                try:
                    os.remove(temp_path)
                except:
                    pass
                return response
            else:
                raise HTTPException(status_code=404, detail="File not found on Drive")
        else:
            # Download from local storage
            return FileResponse(os.path.join(DATA_FOLDER, filename), filename=filename)
    
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/download/data-multiple')
def download_multiple_files(data: dict = Body(...)):
    data_folder = 'Data'
    files = data.get('files', [])
    if not files:
        return JSONResponse({'error': 'No files selected'}, status_code=400)

    # Security check: prevent path traversal attacks
    for filename in files:
        if '..' in filename or filename.startswith('/'):
            return JSONResponse({'error': 'Invalid filename detected'}, status_code=400)

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename in files:
            file_path = os.path.join(data_folder, filename)
            if os.path.isfile(file_path):
                zf.write(file_path, arcname=filename)
            else:
                return JSONResponse({'error': f'File not found: {filename}'}, status_code=404)
    memory_file.seek(0)
    return StreamingResponse(memory_file, media_type='application/zip', headers={
        'Content-Disposition': 'attachment; filename="selected_files.zip"'
    })

class UploadedFileAdapter:
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    def read(self):
        return self._content

    def save(self, filepath):
        with open(filepath, 'wb') as output:
            output.write(self._content)


@app.api_route('/dev', methods=['GET', 'POST'])
async def dev(request: Request, files: list[UploadFile] = File(default=[]),
              json_code: str = Form(default=''), id: str = Form(default='')):
    questions = {}
    errors = []
    if request.method == 'POST':
        uploaded_files = [UploadedFileAdapter(file.filename, await file.read()) for file in files]
        id_filter = id  # Lấy giá trị ID từ form
        if uploaded_files:
            questions_file, errors_file = parse_questions(files=uploaded_files, id_filter=id_filter)  # Thêm câu hỏi vào danh sách
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
    return templates.TemplateResponse(request=request, name='Dev.html', context={
        'questions': sorted_questions,
        'errors': errors,
        'total_questions': total_questions
    })

# Admin authentication decorator
def admin_required(f):
    def check_access(request):
        return request is not None and request.session.get('admin_logged_in') and is_admin(request)

    if inspect.iscoroutinefunction(f):
        @wraps(f)
        async def async_decorated_function(*args, **kwargs):
            request = next((arg for arg in args if isinstance(arg, Request)), kwargs.get('request'))
            if not check_access(request):
                return RedirectResponse(url=str(request.url_for('admin_login')), status_code=303)
            return await f(*args, **kwargs)
        return async_decorated_function

    @wraps(f)
    def decorated_function(*args, **kwargs):
        request = next((arg for arg in args if isinstance(arg, Request)), kwargs.get('request'))
        if not check_access(request):
            # Redirect to OAuth login
            return RedirectResponse(url=str(request.url_for('admin_login')), status_code=303)
        return f(*args, **kwargs)
    return decorated_function

# Admin login page - Show login page with Google button
@app.get('/admin/login')
def admin_login(request: Request, error: str = ''):
    """Show login page with Google OAuth button"""
    error_message = None
    if error == 'access_denied':
        error_message = '🚫 Từ chối truy cập: Bạn là ai?'
    elif error == 'oauth_failed':
        error_message = '❌ Lỗi xác thực: Không thể kết nối với Google'
    return templates.TemplateResponse(request=request, name='admin_login.html', context={'error': error_message})

# Admin OAuth redirect
@app.get('/admin/oauth/login')
async def admin_oauth_login(request: Request):
    """Redirect to Google OAuth login"""
    # Dynamic redirect URI based on request
    redirect_uri = str(request.url_for('admin_callback'))
    return await google.authorize_redirect(request, redirect_uri)

# Admin OAuth callback
@app.get('/admin/callback')
async def admin_callback(request: Request):
    """Handle Google OAuth callback"""
    try:
        token = await google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            return templates.TemplateResponse(request=request, name='admin_login_error.html', context={
                'error': 'Không thể lấy thông tin người dùng từ Google'
            })
        
        email = user_info.get('email')
        name = user_info.get('name')
        picture = user_info.get('picture')
        
        # Check if user is authorized admin
        if email.lower() not in [e.lower() for e in ADMIN_EMAILS]:
            return RedirectResponse(url=str(request.url_for('admin_login')) + '?error=access_denied', status_code=303)
        
        # Set session
        request.session['admin_logged_in'] = True
        request.session['admin_email'] = email
        request.session['admin_name'] = name
        request.session['admin_picture'] = picture
        
        return RedirectResponse(url=str(request.url_for('admin')), status_code=303)
        
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return RedirectResponse(url=str(request.url_for('admin_login')) + '?error=oauth_failed', status_code=303)

# Admin logout
@app.get('/admin/logout')
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=str(request.url_for('admin_login')), status_code=303)

# Admin dashboard
@app.get('/admin')
@admin_required
def admin(request: Request):
    admin_email = request.session.get('admin_email', '')
    admin_name = request.session.get('admin_name', 'Admin')
    admin_picture = request.session.get('admin_picture', '')
    
    # Get visible files based on user permission
    visible_files = get_visible_files(request)
    hidden_files = load_hidden_files() if is_super_admin(request) else []
    
    return templates.TemplateResponse(request=request, name='admin.html', context={
        'admin_name': admin_name,
        'admin_email': admin_email,
        'admin_picture': admin_picture,
        'is_super_admin': is_super_admin(request),
        'hidden_files': hidden_files
    })

# Admin upload file
@app.post('/admin/upload')
@admin_required
async def admin_upload(request: Request, files: list[UploadFile] = File(default=[])):
    if not files:
        return JSONResponse({'error': 'No files provided'}, status_code=400)
    uploaded_files = []
    errors = []
    
    # Get uploader info
    admin_name = request.session.get('admin_name', 'Admin')
    uploader_name = admin_name
    
    for file in files:
        if file and file.filename:
            try:
                uploaded_file = UploadedFileAdapter(file.filename, await file.read())
                if drive_manager:
                    # Upload to Google Drive with uploader info
                    file_id = drive_manager.upload_file_object(uploaded_file, file.filename, uploader_name)
                    if file_id:
                        uploaded_files.append(file.filename)
                    else:
                        errors.append(f"{file.filename}: Failed to upload to Drive")
                else:
                    # Upload to local storage
                    filepath = os.path.join(DATA_FOLDER, file.filename)
                    uploaded_file.save(filepath)
                    uploaded_files.append(file.filename)
                    # Save metadata for local files
                    save_file_metadata(file.filename, uploader_name)
            except Exception as e:
                errors.append(f"{file.filename}: {str(e)}")
    
    return JSONResponse({
        'success': len(uploaded_files),
        'uploaded': uploaded_files,
        'errors': errors
    })

# Admin list files
@app.get('/admin/files')
@admin_required
def admin_files(request: Request):
    try:
        visible_files = get_visible_files(request)
        hidden_files = load_hidden_files() if is_super_admin(request) else []
        
        files = []
        
        if drive_manager:
            # List from Google Drive
            drive_files = drive_manager.list_files()
            for file in drive_files:
                # Skip hidden files if not super admin
                if file['name'] not in visible_files and not is_super_admin(request):
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
                if filename not in visible_files and not is_super_admin(request):
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
        
        return JSONResponse(files)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)

# Admin delete file
@app.delete('/admin/delete/{filename}')
@admin_required
def admin_delete(request: Request, filename: str):
    try:
        if '..' in filename or filename.startswith('/'):
            return JSONResponse({'error': 'Invalid filename'}, status_code=400)
        
        if drive_manager:
            # Delete from Google Drive
            success = drive_manager.delete_file_by_name(filename)
            if success:
                return JSONResponse({'success': True, 'message': f'Deleted {filename}'})
            else:
                return JSONResponse({'error': 'File not found or delete failed'}, status_code=404)
        else:
            # Delete from local storage
            filepath = os.path.join(DATA_FOLDER, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
                return JSONResponse({'success': True, 'message': f'Deleted {filename}'})
            else:
                return JSONResponse({'error': 'File not found'}, status_code=404)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)

# Toggle file visibility (super admin only)
@app.post('/admin/toggle_visibility')
@admin_required
def toggle_file_visibility(request: Request, data: dict = Body(...)):
    """Toggle ẩn/hiện file - chỉ super admin (minhmuc) mới làm được"""
    if not is_super_admin(request):
        return JSONResponse({'success': False, 'error': 'Chỉ minhmuc mới có quyền ẩn/hiện file'}, status_code=403)
    
    filename = data.get('filename')
    
    if not filename:
        return JSONResponse({'success': False, 'error': 'Missing filename'}, status_code=400)
    
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
    
    return JSONResponse({
        'success': True,
        'action': action,
        'filename': filename,
        'hidden_files': hidden_files
    })

# Get hidden files list (super admin only)
@app.get('/admin/hidden_files')
@admin_required
def get_hidden_files_route(request: Request):
    """Lấy danh sách file ẩn - chỉ super admin thấy được"""
    if not is_super_admin(request):
        return JSONResponse({'success': False, 'error': 'Unauthorized'}, status_code=403)
    
    hidden_files = load_hidden_files()
    return JSONResponse({'success': True, 'hidden_files': hidden_files})

# SEO Routes
@app.get('/robots.txt')
def robots():
    """Serve robots.txt file"""
    return FileResponse('robots.txt')

@app.get('/sitemap.xml')
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
    
    return Response(sitemap_xml, media_type='text/xml')

# Admin download multiple files as zip
@app.post('/admin/download-multiple')
@admin_required
def admin_download_multiple(request: Request, data: dict = Body(...)):
    try:
        filenames = data.get('files', [])
        
        if not filenames:
            return JSONResponse({'error': 'No files specified'}, status_code=400)
        
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
        return StreamingResponse(memory_file, media_type='application/zip', headers={
            'Content-Disposition': f'attachment; filename="files_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip"'
        })
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get('PORT', 5000))
    uvicorn.run(app, host='0.0.0.0', port=port)
