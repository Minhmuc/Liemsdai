"""
Setup OAuth token for Google Drive
Run this once to authorize your Google account
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive']

def setup_oauth():
    """Setup OAuth authentication and save token"""
    creds = None
    
    # Check if token already exists
    if os.path.exists('token.json'):
        print("✅ token.json already exists")
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if creds and creds.valid:
            print("✅ Token is valid!")
            return True
        
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
            print("✅ Token refreshed!")
            return True
    
    # Need to create new credentials
    if not os.path.exists('credentials.json'):
        print("❌ credentials.json not found!")
        print("\n📝 Steps to get credentials.json:")
        print("1. Go to: https://console.cloud.google.com")
        print("2. Create/Select project")
        print("3. Enable Google Drive API")
        print("4. Go to Credentials → Create Credentials → OAuth 2.0 Client ID")
        print("5. Application type: Desktop app")
        print("6. Download JSON and save as credentials.json")
        return False
    
    print("🔐 Starting OAuth flow...")
    print("A browser window will open for authorization...")
    
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    
    # Save credentials
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
    
    print("✅ OAuth setup complete!")
    print("✅ token.json created")
    print("\n📋 Next steps:")
    print("1. Upload token.json to Render as a Secret File")
    print("2. Your app will now use OAuth authentication")
    print("3. Files will be stored in YOUR Google Drive (15GB free)")
    
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("Google Drive OAuth Setup")
    print("=" * 60)
    print()
    
    success = setup_oauth()
    
    if success:
        print("\n✅ Setup successful!")
        print("You can now use Google Drive with your personal account.")
    else:
        print("\n❌ Setup failed!")
        print("Please follow the instructions above.")
