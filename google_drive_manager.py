"""
Google Drive Manager for LMS Licker
Upload, download, list, and delete files from Google Drive
"""

import os
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

class GoogleDriveManager:
    def __init__(self, credentials_file='credentials.json', folder_id=None):
        """
        Initialize Google Drive Manager
        
        Args:
            credentials_file: Path to service account JSON file
            folder_id: Google Drive folder ID to store files (optional)
        """
        self.credentials_file = credentials_file
        self.folder_id = folder_id
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Drive API using OAuth or Service Account"""
        try:
            SCOPES = ['https://www.googleapis.com/auth/drive']
            
            # Try OAuth first (token.json), fallback to Service Account
            if os.path.exists('token.json'):
                print("🔑 Using OAuth authentication (token.json)")
                from google.auth.transport.requests import Request
                from google.oauth2.credentials import Credentials
                from google_auth_oauthlib.flow import InstalledAppFlow
                
                creds = None
                if os.path.exists('token.json'):
                    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                
                # If no valid credentials, let user log in
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        print("🔄 Refreshing expired token...")
                        creds.refresh(Request())
                    else:
                        print("⚠️ Need to authorize. Run setup script first!")
                        raise Exception("OAuth token not found or invalid")
                    
                    # Save credentials
                    with open('token.json', 'w') as token:
                        token.write(creds.to_json())
                
                self.service = build('drive', 'v3', credentials=creds)
                print("✅ OAuth authenticated successfully")
            else:
                print("🔑 Using Service Account authentication (credentials.json)")
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_file, scopes=SCOPES)
                self.service = build('drive', 'v3', credentials=credentials)
                print("⚠️ Warning: Service Accounts have no storage quota!")
                print("   Use OAuth authentication instead (create token.json)")
                
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            raise
    
    def upload_file(self, file_path, filename=None):
        """
        Upload a file to Google Drive
        
        Args:
            file_path: Local file path to upload
            filename: Name to save on Drive (defaults to original filename)
        
        Returns:
            File ID on success, None on failure
        """
        try:
            if not filename:
                filename = os.path.basename(file_path)
            
            if not os.path.exists(file_path):
                print(f"❌ File not found: {file_path}")
                return None
            
            file_size = os.path.getsize(file_path)
            print(f"📄 Uploading {filename} ({file_size} bytes)")
            
            file_metadata = {
                'name': filename,
            }
            
            # Add to folder if specified
            if self.folder_id:
                file_metadata['parents'] = [self.folder_id]
                print(f"📁 Uploading to folder: {self.folder_id}")
            
            media = MediaFileUpload(file_path, resumable=True)
            
            print(f"🔄 Executing Drive API create...")
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, size, createdTime'
            ).execute()
            
            print(f"✅ Uploaded: {filename} (ID: {file.get('id')}, Size: {file.get('size')})")
            return file.get('id')
        
        except HttpError as error:
            print(f"❌ HTTP Error during upload: {error}")
            print(f"   Error details: {error.error_details if hasattr(error, 'error_details') else 'N/A'}")
            import traceback
            traceback.print_exc()
            return None
        except Exception as error:
            print(f"❌ Unexpected error during upload: {error}")
            import traceback
            traceback.print_exc()
            return None
    
    def upload_file_object(self, file_object, filename):
        """
        Upload a file from memory (Flask file object)
        
        Args:
            file_object: File object from Flask request.files
            filename: Name to save on Drive
        
        Returns:
            File ID on success, None on failure
        """
        temp_path = None
        try:
            print(f"📤 Starting upload: {filename}")
            
            file_metadata = {
                'name': filename,
            }
            
            if self.folder_id:
                file_metadata['parents'] = [self.folder_id]
                print(f"📁 Target folder ID: {self.folder_id}")
            
            # Create temp directory if not exists (works on Windows & Linux)
            import tempfile
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, filename)
            
            print(f"💾 Saving to temp: {temp_path}")
            
            # Reset file pointer to beginning
            file_object.seek(0)
            
            # Save to temp file
            file_object.save(temp_path)
            
            # Verify file was saved
            if not os.path.exists(temp_path):
                print(f"❌ Temp file not created: {temp_path}")
                return None
            
            file_size = os.path.getsize(temp_path)
            print(f"✅ Temp file saved: {file_size} bytes")
            
            # Upload the temp file
            print(f"☁️ Uploading to Google Drive...")
            result = self.upload_file(temp_path, filename)
            
            if result:
                print(f"✅ Upload successful! File ID: {result}")
            else:
                print(f"❌ Upload failed - no file ID returned")
            
            return result
        
        except Exception as error:
            print(f"❌ Upload error for {filename}: {error}")
            import traceback
            traceback.print_exc()
            return None
        
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"🗑️ Cleaned up temp file: {temp_path}")
                except Exception as e:
                    print(f"⚠️ Could not clean temp file: {e}")
    
    def download_file(self, file_id, destination_path):
        """
        Download a file from Google Drive
        
        Args:
            file_id: Google Drive file ID
            destination_path: Local path to save file
        
        Returns:
            True on success, False on failure
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_handle = io.FileIO(destination_path, 'wb')
            downloader = MediaIoBaseDownload(file_handle, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            file_handle.close()
            print(f"✅ Downloaded to: {destination_path}")
            return True
        
        except HttpError as error:
            print(f"❌ Download error: {error}")
            return False
    
    def download_file_by_name(self, filename, destination_path):
        """
        Download a file by its name
        
        Args:
            filename: Name of file on Drive
            destination_path: Local path to save file
        
        Returns:
            True on success, False on failure
        """
        try:
            file_id = self.get_file_id_by_name(filename)
            if file_id:
                return self.download_file(file_id, destination_path)
            else:
                print(f"❌ File not found: {filename}")
                return False
        except Exception as error:
            print(f"❌ Error: {error}")
            return False
    
    def list_files(self):
        """
        List all files in the Drive folder
        
        Returns:
            List of file dictionaries with name, id, size, modifiedTime
        """
        try:
            query = f"'{self.folder_id}' in parents and trashed=false" if self.folder_id else "trashed=false"
            
            results = self.service.files().list(
                q=query,
                pageSize=1000,
                fields="files(id, name, size, modifiedTime, mimeType)"
            ).execute()
            
            files = results.get('files', [])
            return files
        
        except HttpError as error:
            print(f"❌ List error: {error}")
            return []
    
    def get_file_id_by_name(self, filename):
        """
        Get file ID by filename
        
        Args:
            filename: Name of the file
        
        Returns:
            File ID or None if not found
        """
        try:
            query = f"name='{filename}' and trashed=false"
            if self.folder_id:
                query += f" and '{self.folder_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                pageSize=1,
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            return None
        
        except HttpError as error:
            print(f"❌ Search error: {error}")
            return None
    
    def delete_file(self, file_id):
        """
        Delete a file from Google Drive
        
        Args:
            file_id: Google Drive file ID
        
        Returns:
            True on success, False on failure
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            print(f"✅ Deleted file ID: {file_id}")
            return True
        
        except HttpError as error:
            print(f"❌ Delete error: {error}")
            return False
    
    def delete_file_by_name(self, filename):
        """
        Delete a file by its name
        
        Args:
            filename: Name of file to delete
        
        Returns:
            True on success, False on failure
        """
        try:
            file_id = self.get_file_id_by_name(filename)
            if file_id:
                return self.delete_file(file_id)
            else:
                print(f"❌ File not found: {filename}")
                return False
        except Exception as error:
            print(f"❌ Error: {error}")
            return False
    
    def get_file_info(self, filename):
        """
        Get file information
        
        Args:
            filename: Name of the file
        
        Returns:
            Dictionary with file info or None
        """
        try:
            files = self.list_files()
            for file in files:
                if file['name'] == filename:
                    return file
            return None
        except Exception as error:
            print(f"❌ Error: {error}")
            return None


# Example usage
if __name__ == "__main__":
    # Initialize manager
    # Replace with your folder ID from Google Drive URL
    # Example: https://drive.google.com/drive/folders/1ABC...XYZ
    # Folder ID is: 1ABC...XYZ
    
    manager = GoogleDriveManager(
        credentials_file='credentials.json',
        folder_id='YOUR_FOLDER_ID_HERE'  # Optional
    )
    
    # List files
    files = manager.list_files()
    print(f"Total files: {len(files)}")
    for file in files:
        print(f"- {file['name']} (Size: {file.get('size', 'N/A')} bytes)")
