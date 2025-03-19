from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import csv
import uuid
from typing import List, Optional
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "https://google-drive-extractor.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Models
# ---------------------------
class ScanRequest(BaseModel):
    folder_id: str

class FileInfo(BaseModel):
    name: str
    link: str
    size: Optional[str]
    file_type: str
    entire_folder_path: str

class ScanResponse(BaseModel):
    job_id: str
    message: str

class ScanResult(BaseModel):
    files: List[FileInfo]
    total_count: int

# ---------------------------
# Google Drive Functions
# ---------------------------
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

def authenticate():
    """Authenticates the user and returns valid credentials."""
    creds = None
    
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds

def get_drive_link(file):
    """Returns the Google Drive link for the given file ID."""
    file_id = file.get('id')
    return f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"

def list_files(service, folder_id='root', current_path=""):
    """Recursively list files from the specified folder in Google Drive."""
    results = []
    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None
    
    while True:
        response = service.files().list(
            q=query,
            spaces='drive',
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageToken=page_token
        ).execute()

        files = response.get('files', [])
        
        for file in files:
            file_info = {
                'name': file.get('name'),
                'entire_folder_path': current_path,
                'file_type': file.get('mimeType'),
                'link': get_drive_link(file),
                'size': file.get('size', 'N/A')
            }
            results.append(file_info)

            if file.get('mimeType') == 'application/vnd.google-apps.folder':
                new_path = file.get('name') if not current_path else current_path + "/" + file.get('name')
                results.extend(list_files(service, folder_id=file.get('id'), current_path=new_path))
                
        page_token = response.get('nextPageToken', None)
        if not page_token:
            break

    return results

def export_to_csv(files, output_file):
    """Writes the file information to a CSV file."""
    with open(output_file, mode='w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['name', 'link', 'size', 'file_type', 'entire_folder_path']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for file in files:
            writer.writerow(file)

# Job storage
scan_jobs = {}

# ---------------------------
# API Endpoints
# ---------------------------
@app.post("/api/scan", response_model=ScanResponse)
async def start_scan(scan_request: ScanRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    
    # Add task to background
    background_tasks.add_task(process_scan, job_id, scan_request.folder_id)
    
    return ScanResponse(
        job_id=job_id,
        message="Scan started"
    )

@app.get("/api/scan/{job_id}/status")
async def get_scan_status(job_id: str):
    if job_id not in scan_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = scan_jobs[job_id]
    return {
        "status": job["status"],
        "message": job["message"],
        "progress": job.get("progress", 0)
    }

@app.get("/api/scan/{job_id}/download")
async def download_results(job_id: str):
    if job_id not in scan_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = scan_jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Scan not completed yet")
    
    csv_file = f"scan_results_{job_id}.csv"
    if not os.path.exists(csv_file):
        raise HTTPException(status_code=404, detail="Result file not found")
    
    return FileResponse(
        csv_file,
        media_type="text/csv",
        filename="google_drive_scan.csv"
    )

# ---------------------------
# Background Tasks
# ---------------------------
def process_scan(job_id: str, folder_id: str):
    scan_jobs[job_id] = {
        "status": "processing",
        "message": "Authentication in progress",
        "progress": 0
    }
    
    try:
        # Authenticate
        scan_jobs[job_id]["message"] = "Authenticating with Google Drive"
        creds = authenticate()
        service = build('drive', 'v3', credentials=creds)
        
        # Scan Drive
        scan_jobs[job_id]["message"] = "Scanning Google Drive"
        scan_jobs[job_id]["progress"] = 10
        files = list_files(service, folder_id=folder_id)
        
        # Export to CSV
        scan_jobs[job_id]["message"] = "Exporting results to CSV"
        scan_jobs[job_id]["progress"] = 90
        csv_file = f"scan_results_{job_id}.csv"
        export_to_csv(files, csv_file)
        
        # Complete
        scan_jobs[job_id]["status"] = "completed"
        scan_jobs[job_id]["message"] = f"Found {len(files)} files and folders"
        scan_jobs[job_id]["progress"] = 100
        scan_jobs[job_id]["file_count"] = len(files)
        
    except Exception as e:
        scan_jobs[job_id]["status"] = "failed"
        scan_jobs[job_id]["message"] = f"Error: {str(e)}"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)