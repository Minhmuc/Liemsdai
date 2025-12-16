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
        """Authenticate with Google Drive API"""
        try:
            SCOPES = ['https://www.googleapis.com/auth/drive']
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file, scopes=SCOPES)
            self.service = build('drive', 'v3', credentials=credentials)
            print("✅ Google Drive authenticated successfully")
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
            
            file_metadata = {
                'name': filename,
            }
            
            # Add to folder if specified
            if self.folder_id:
                file_metadata['parents'] = [self.folder_id]
            
            media = MediaFileUpload(file_path, resumable=True)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, size, createdTime'
            ).execute()
            
            print(f"✅ Uploaded: {filename} (ID: {file.get('id')})")
            return file.get('id')
        
        except HttpError as error:
            print(f"❌ Upload error: {error}")
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
        try:
            file_metadata = {
                'name': filename,
            }
            
            if self.folder_id:
                file_metadata['parents'] = [self.folder_id]
            
            # Save to temp file first
            temp_path = f'/tmp/{filename}'
            file_object.save(temp_path)
            
            result = self.upload_file(temp_path, filename)
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return result
        
        except Exception as error:
            print(f"❌ Upload error: {error}")
            return None
    
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
