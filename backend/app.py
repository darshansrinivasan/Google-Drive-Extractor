from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel, validator
import os
from dotenv import load_dotenv
import csv
import uuid
import json
from typing import List, Optional, Dict, Any
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Google Drive Scanner API",
    description="API for scanning and exporting Google Drive folder contents",
    version="1.0.0",
    docs_url=None,
    redoc_url=None
)

# Configure CORS with more permissive settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
    expose_headers=["*"]  # Exposes all headers
)

# Store credentials in memory (not ideal for production, but works for now)
credentials_store = {}
scan_jobs = {}

# Get Google OAuth credentials from environment variables
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI')

# Log configuration on startup
logger.info("Starting application...")
logger.info(f"GOOGLE_REDIRECT_URI: {GOOGLE_REDIRECT_URI}")

if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI]):
    logger.warning("Google OAuth credentials not properly configured!")
    logger.warning(f"GOOGLE_CLIENT_ID configured: {bool(GOOGLE_CLIENT_ID)}")
    logger.warning(f"GOOGLE_REDIRECT_URI configured: {bool(GOOGLE_REDIRECT_URI)}")

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

class AuthResponse(BaseModel):
    authorization_url: str

# ---------------------------
# Google Drive Functions
# ---------------------------
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

def get_oauth_flow():
    """Create and return OAuth flow object."""
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    redirect_uri = os.getenv('GOOGLE_REDIRECT_URI')
    
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Google credentials not configured")
        
    return InstalledAppFlow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        SCOPES,
        redirect_uri=redirect_uri
    )

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

# ---------------------------
# API Endpoints
# ---------------------------
@app.options("/api/scan")
async def options_scan():
    """Handle OPTIONS request for /api/scan endpoint."""
    return {}

@app.post("/api/scan")
async def scan_folder(request: ScanRequest, background_tasks: BackgroundTasks):
    """Start a folder scan."""
    try:
        job_id = str(uuid.uuid4())
        background_tasks.add_task(process_scan, job_id, request.folder_id)
        return ScanResponse(job_id=job_id, message="Scan started")
    except Exception as e:
        logger.error(f"Scan error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/scan/{job_id}/status")
async def get_scan_status(job_id: str):
    """Get the status of a scan job."""
    if job_id not in scan_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = scan_jobs[job_id]
    response = {
        "status": job["status"],
        "message": job["message"],
        "progress": job.get("progress", 0)
    }
    
    if "authorization_url" in job:
        response["authorization_url"] = job["authorization_url"]
        
    return response

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

@app.get("/oauth2callback")
async def oauth2callback(request: Request):
    """Handle the OAuth 2.0 callback from Google."""
    try:
        code = request.query_params.get("code")
        if not code:
            return RedirectResponse(url="https://google-drive-extractor.vercel.app?error=no_code")
        
        flow = get_oauth_flow()
        flow.fetch_token(code=code)
        
        # Store credentials in memory
        creds_json = flow.credentials.to_json()
        credentials_store['current'] = json.loads(creds_json)
        
        return RedirectResponse(url="https://google-drive-extractor.vercel.app?status=success")
    except Exception as e:
        print(f"OAuth callback error: {str(e)}")
        return RedirectResponse(url=f"https://google-drive-extractor.vercel.app?error={str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        return {
            "status": "healthy",
            "environment": os.getenv('ENVIRONMENT', 'production'),
            "google_auth": {
                "client_id_configured": bool(GOOGLE_CLIENT_ID),
                "client_secret_configured": bool(GOOGLE_CLIENT_SECRET),
                "redirect_uri_configured": bool(GOOGLE_REDIRECT_URI),
                "has_credentials": "current" in credentials_store
            },
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint that redirects to API documentation."""
    return {
        "message": "Welcome to Google Drive Scanner API",
        "version": "1.0.0",
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "scan": "/api/scan",
            "scan_status": "/api/scan/{job_id}/status",
            "scan_download": "/api/scan/{job_id}/download",
            "oauth_callback": "/oauth2callback"
        },
        "documentation": "Visit /docs for complete API documentation"
    }

@app.get("/docs")
async def custom_swagger_ui_html():
    """Custom Swagger UI documentation."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Google Drive Scanner API Documentation",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

# ---------------------------
# Background Tasks
# ---------------------------
def process_scan(job_id: str, folder_id: str):
    """Process the scan in the background."""
    scan_jobs[job_id] = {
        "status": "processing",
        "message": "Starting scan",
        "progress": 0
    }
    
    try:
        # Check if we have valid credentials
        if 'current' not in credentials_store:
            # Start OAuth flow
            flow = get_oauth_flow()
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )
            scan_jobs[job_id].update({
                "status": "auth_required",
                "message": "Authentication required",
                "authorization_url": authorization_url
            })
            return
            
        # Build the service using stored credentials
        creds = Credentials.from_authorized_user_info(credentials_store['current'], SCOPES)
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
        scan_jobs[job_id].update({
            "status": "completed",
            "message": f"Found {len(files)} files and folders",
            "progress": 100,
            "file_count": len(files)
        })
        
    except Exception as e:
        print(f"Scan error: {str(e)}")
        scan_jobs[job_id].update({
            "status": "failed",
            "message": f"Error: {str(e)}"
        })

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests."""
    logger.info(f"Request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.info(f"Response: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)