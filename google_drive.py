from __future__ import print_function
import pickle
import re
import io
import os.path
import json
import time
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = 'google_drive_credentials.json'
TOKEN_PICKLE_FILE = 'google_drive_token.pickle'


def get_venmo_code(since_time):
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_PICKLE_FILE):
        with open(TOKEN_PICKLE_FILE, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PICKLE_FILE, 'wb') as token:
            pickle.dump(creds, token)

    service = build('drive', 'v3', credentials=creds)

    # Call the Drive v3 API
    results = service.files().list(
        pageSize=10, fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])

    lastsms_file_id = None
    if not items:
        print('No files found.')
    else:
        print('Files:')
        for item in items:
            if 'lastsms' in item['name']:
                lastsms_file_id = item['id']
                print(u'{0} ({1})'.format(item['name'], item['id']))
    if lastsms_file_id == None:
        print("lastsms file not found (I didn't look very hard)")
        return None
    request = service.files().get_media(fileId=lastsms_file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    lastsms = json.load(fh)
    venmo_pattern = re.compile("Venmo here\!.*Code: ([0-9]+)")
    for text in lastsms:
        if not 'text' in text:
            continue
        if text['date'] < since_time:
            continue
        match = venmo_pattern.match(text['text'])
        if match != None:
            return match.group(1)
    return None


if __name__ == '__main__':
    print(get_venmo_code(time.time() * 1000))
