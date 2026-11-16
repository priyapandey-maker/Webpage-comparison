const API_BASE_URL = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL)
  ? import.meta.env.VITE_API_BASE_URL
  : 'http://127.0.0.1:8000';

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

export async function compareUrls(url1, url2, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/compare-urls`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url1, url2 }),
      signal: options?.signal,
    });
  } catch (networkError) {
    if (networkError.name === 'AbortError') {
      throw networkError;
    }
    throw new Error('Unable to reach the comparison service. Please ensure the backend is running and accessible.');
  }

  if (!response.ok) {
    let message = 'Comparison failed. Please check both URLs and try again.';
    try {
      const error = await response.json();
      if (typeof error?.detail === 'string' && error.detail.trim()) {
        message = error.detail.trim();
      } else if (Array.isArray(error?.detail) && error.detail.length > 0) {
        const firstErr = error.detail[0];
        message = firstErr.msg || 'Validation failed for the requested URLs.';
      }
    } catch {
      if (response.status === 400) {
        message = 'The requested URL was rejected by security validation.';
      } else if (response.status === 413) {
        message = 'The target webpage exceeded the maximum allowed size of 10 MB.';
      } else if (response.status === 415) {
        message = 'The target webpage returned an unsupported format. Only HTML pages can be compared.';
      } else if (response.status === 422) {
        message = 'The webpage content is empty or contains unparseable HTML.';
      } else if (response.status === 502) {
        message = 'Upstream server error: could not fetch the webpage from the target server.';
      } else if (response.status === 504) {
        message = 'Request timed out while waiting for the target webpage to respond.';
      }
    }
    throw new Error(message);
  }

  return response.json();
}

export async function getWaybackSnapshots(url, fromYear, toYear, options = {}) {
  const params = new URLSearchParams({ url: (url || '').trim() });
  if (fromYear != null && String(fromYear).trim()) {
    params.append('from_year', String(fromYear).trim());
  }
  if (toYear != null && String(toYear).trim()) {
    params.append('to_year', String(toYear).trim());
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/wayback/snapshots?${params.toString()}`, {
      method: 'GET',
      signal: options?.signal,
    });
  } catch (networkError) {
    if (networkError.name === 'AbortError') {
      throw networkError;
    }
    throw new Error('Unable to reach the Wayback snapshot discovery service. Please ensure the backend is running and accessible.');
  }

  if (!response.ok) {
    let message = 'Snapshot discovery failed. Please check the URL and try again.';
    try {
      const error = await response.json();
      if (typeof error?.detail === 'string' && error.detail.trim()) {
        message = error.detail.trim();
      } else if (Array.isArray(error?.detail) && error.detail.length > 0) {
        const firstErr = error.detail[0];
        message = firstErr.msg || 'Validation failed for the snapshot discovery request.';
      }
    } catch {
      if (response.status === 400) {
        message = 'The requested URL or year filter was rejected by validation.';
      } else if (response.status === 502) {
        message = 'Unable to communicate with Internet Archive Wayback Machine services.';
      } else if (response.status === 504) {
        message = 'Request timed out while searching the Wayback Machine for snapshots.';
      }
    }
    throw new Error(message);
  }

  return response.json();
}

export async function compareWaybackSnapshots(url, timestamp1, timestamp2, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}/api/wayback/compare`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: (url || '').trim(),
        timestamp1: (timestamp1 || '').trim(),
        timestamp2: (timestamp2 || '').trim(),
      }),
      signal: options?.signal,
    });
  } catch (networkError) {
    if (networkError.name === 'AbortError') {
      throw networkError;
    }
    throw new Error('Unable to reach the comparison service. Please ensure the backend is running and accessible.');
  }

  if (!response.ok) {
    let message = 'Historical comparison failed. Please try again.';
    try {
      const error = await response.json();
      if (typeof error?.detail === 'string' && error.detail.trim()) {
        message = error.detail.trim();
      } else if (Array.isArray(error?.detail) && error.detail.length > 0) {
        const firstErr = error.detail[0];
        message = firstErr.msg || 'Validation failed for the requested snapshots.';
      }
    } catch {
      if (response.status === 400) {
        message = 'Invalid comparison request. Please select two distinct valid snapshots.';
      } else if (response.status === 404) {
        message = 'One or both of the selected snapshots were not found in the archive index.';
      } else if (response.status === 409) {
        message = 'Exact capture unavailable: Wayback redirected to a different timestamp.';
      } else if (response.status === 413) {
        message = 'Archived webpage capture exceeded the maximum allowed size of 10 MB.';
      } else if (response.status === 422) {
        message = 'Archived content is unparseable or contains non-HTML data.';
      } else if (response.status === 502) {
        message = 'Upstream archive error: could not retrieve historical captures from the Wayback Machine.';
      } else if (response.status === 504) {
        message = 'Request timed out while retrieving historical captures from the Wayback Machine.';
      }
    }
    throw new Error(message);
  }

  return response.json();
}
