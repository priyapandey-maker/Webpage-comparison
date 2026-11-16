const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export async function compareFiles(version1File, version2File) {
  const formData = new FormData();
  formData.append('version1', version1File);
  formData.append('version2', version2File);

  const response = await fetch(`${API_BASE_URL}/api/compare`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let message = 'Comparison failed. Please check both HTML files and try again.';
    try {
      const error = await response.json();
      if (error.detail) message = error.detail;
    } catch {
      // Keep the factual fallback when the server response is not JSON.
    }
    throw new Error(message);
  }

  return response.json();
}
