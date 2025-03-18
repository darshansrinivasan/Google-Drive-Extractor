# Google Drive Scanner

A web application that allows users to scan their Google Drive for files and folders.

## Features

- Google Drive authentication
- File and folder scanning
- Modern UI with Next.js and Tailwind CSS
- FastAPI backend with Google Drive API integration

## Prerequisites

- Python 3.11+
- Node.js 18+
- Google Cloud Platform account with Drive API enabled
- Google OAuth 2.0 credentials

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/google-drive-scanner.git
cd google-drive-scanner
```

2. Set up the backend:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up the frontend:
```bash
cd frontend
npm install
```

4. Configure Google OAuth:
- Go to Google Cloud Console
- Create a new project
- Enable the Google Drive API
- Create OAuth 2.0 credentials
- Download the credentials and save as `backend/credentials.json`

5. Start the development servers:

Backend:
```bash
cd backend
source venv/bin/activate
uvicorn app:app --reload
```

Frontend:
```bash
cd frontend
npm run dev
```

The application will be available at:
- Frontend: http://localhost:3000
- Backend: http://localhost:8000

## Deployment

The application can be deployed to:
- Frontend: Vercel
- Backend: Heroku or any other Python hosting service

## License

MIT 