import { useState, useEffect } from 'react';
import Head from 'next/head';
import axios from 'axios';

// API base URL - change this in production
const API_URL = 'http://localhost:8000';

export default function Home() {
  const [folderId, setFolderId] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);

  // Status polling
  useEffect(() => {
    let intervalId;
    
    if (jobId && isScanning) {
      intervalId = setInterval(async () => {
        try {
          const response = await axios.get(`${API_URL}/api/scan/${jobId}/status`);
          setStatus(response.data);
          setProgress(response.data.progress || 0);
          
          if (response.data.status === 'completed' || response.data.status === 'failed') {
            setIsScanning(false);
            clearInterval(intervalId);
          }
        } catch (err) {
          console.error('Error checking status:', err);
          setError('Failed to get scan status');
          setIsScanning(false);
          clearInterval(intervalId);
        }
      }, 2000);
    }
    
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [jobId, isScanning]);

  // Start the scan
  const handleScan = async (e) => {
    e.preventDefault();
    if (!folderId) {
      setError('Please enter a Google Drive Folder ID');
      return;
    }
    
    setError(null);
    setIsScanning(true);
    
    try {
      const response = await axios.post(`${API_URL}/api/scan`, {
        folder_id: folderId
      });
      
      setJobId(response.data.job_id);
    } catch (err) {
      console.error('Error starting scan:', err);
      setError('Failed to start the scan');
      setIsScanning(false);
    }
  };

  // Download results
  const handleDownload = () => {
    if (jobId) {
      window.location.href = `${API_URL}/api/scan/${jobId}/download`;
    }
  };

  const scanDrive = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axios.get(`${process.env.NEXT_PUBLIC_API_URL}/api/scan`);
      setFiles(response.data.files);
    } catch (err) {
      setError('Failed to scan Google Drive. Please try again.');
      console.error('Error scanning drive:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <Head>
        <title>Google Drive Scanner</title>
        <meta name="description" content="Scan and export Google Drive files" />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <main className="container mx-auto py-10 px-4">
        <div className="max-w-2xl mx-auto bg-white p-8 rounded-lg shadow-md">
          <h1 className="text-3xl font-bold mb-6 text-center text-blue-600">
            Google Drive Scanner
          </h1>
          
          <form onSubmit={handleScan} className="mb-8">
            <div className="mb-4">
              <label htmlFor="folderId" className="block text-gray-700 font-medium mb-2">
                Google Drive Folder ID
              </label>
              <input
                type="text"
                id="folderId"
                value={folderId}
                onChange={(e) => setFolderId(e.target.value)}
                placeholder="Enter your Google Drive folder ID"
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                disabled={isScanning}
              />
              <p className="text-sm text-gray-500 mt-1">
                You can find the folder ID in the URL when you open the folder in Google Drive
              </p>
            </div>
            
            <button
              type="submit"
              disabled={isScanning || !folderId}
              className={`w-full py-2 px-4 rounded-md text-white font-medium ${
                isScanning || !folderId 
                  ? 'bg-blue-300 cursor-not-allowed' 
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {isScanning ? 'Scanning...' : 'Start Scan'}
            </button>
          </form>
          
          {error && (
            <div className="mb-6 p-4 bg-red-100 border-l-4 border-red-500 text-red-700">
              <p>{error}</p>
            </div>
          )}
          
          {isScanning && (
            <div className="mb-6">
              <h3 className="text-lg font-medium mb-2">Scanning in progress...</h3>
              <div className="w-full bg-gray-200 rounded-full h-4 mb-2">
                <div 
                  className="bg-blue-600 h-4 rounded-full" 
                  style={{ width: `${progress}%` }}
                ></div>
              </div>
              <p className="text-gray-600">{status?.message || 'Processing...'}</p>
            </div>
          )}
          
          {status?.status === 'completed' && (
            <div className="mb-6 p-4 bg-green-100 border-l-4 border-green-500 text-green-700">
              <p className="mb-2">{status.message}</p>
              <button
                onClick={handleDownload}
                className="py-2 px-4 bg-green-600 text-white rounded-md hover:bg-green-700"
              >
                Download CSV
              </button>
            </div>
          )}
          
          {status?.status === 'failed' && (
            <div className="mb-6 p-4 bg-red-100 border-l-4 border-red-500 text-red-700">
              <p>Failed: {status.message}</p>
            </div>
          )}
          
          <div className="mt-8 border-t pt-6">
            <h2 className="text-xl font-semibold mb-3">How to use</h2>
            <ol className="list-decimal pl-6 space-y-2">
              <li>Find the Folder ID from your Google Drive folder URL</li>
              <li>Enter the Folder ID in the input field above</li>
              <li>Click "Start Scan" to begin the scanning process</li>
              <li>Wait for the scan to complete</li>
              <li>Download the CSV file with your Google Drive content</li>
            </ol>
          </div>

          <div className="mt-8 border-t pt-6">
            <h2 className="text-xl font-semibold mb-3">Scan Drive</h2>
            <button
              onClick={scanDrive}
              disabled={loading}
              className={`w-full py-2 px-4 rounded-md text-white font-medium ${
                loading
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {loading ? 'Scanning...' : 'Scan Drive'}
            </button>
          </div>

          {files.length > 0 && (
            <div className="mt-8">
              <h2 className="text-xl font-semibold mb-4">Files Found:</h2>
              <ul className="space-y-2">
                {files.map((file) => (
                  <li
                    key={file.id}
                    className="p-3 bg-gray-50 rounded-md hover:bg-gray-100 transition-colors"
                  >
                    <div className="font-medium">{file.name}</div>
                    <div className="text-sm text-gray-500">
                      Type: {file.mimeType}
                    </div>
                    <div className="text-sm text-gray-500">
                      Modified: {new Date(file.modifiedTime).toLocaleString()}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}