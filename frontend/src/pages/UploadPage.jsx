import { useState } from 'react';
import FileDropZone from '../components/FileDropZone';

export default function UploadPage({ onCompare }) {
  const [version1File, setVersion1File] = useState(null);
  const [version2File, setVersion2File] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    if (!version1File || !version2File || isLoading) return;

    setIsLoading(true);
    setError('');
    try {
      await onCompare(version1File, version2File);
    } catch (comparisonError) {
      setError(comparisonError.message || 'Comparison failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="upload-page">
      <div className="upload-shell">
        <header className="upload-header">
          <div className="eyebrow">Webpage analysis tool</div>
          <h1>Historical Webpage Comparison</h1>
          <p>Compare two versions of a webpage to understand what changed.</p>
        </header>

        <form className="upload-panel" onSubmit={handleSubmit}>
          <div className="upload-intro">
            <div>
              <span className="section-number">01</span>
              <h2>Select webpage versions</h2>
            </div>
            <p>Choose the older webpage first, followed by the newer version. Both files will be compared to identify structural and content changes.</p>
          </div>

          <div className="upload-grid">
            <FileDropZone
              id="version-1"
              label="Version 1"
              subtitle="Older webpage"
              file={version1File}
              onFileChange={setVersion1File}
            />
            <FileDropZone
              id="version-2"
              label="Version 2"
              subtitle="Newer webpage"
              file={version2File}
              onFileChange={setVersion2File}
            />
          </div>

          <div className="compare-action">
            {error && <p className="file-error comparison-error" role="alert">{error}</p>}
            <button
              className="primary-button"
              type="submit"
              disabled={!version1File || !version2File || isLoading}
            >
              {isLoading ? 'Preparing comparison results...' : 'Compare Versions'}
            </button>
            <span className="loading-status" role="status" aria-live="polite">
              {isLoading ? 'Preparing comparison results...' : ''}
            </span>
          </div>
        </form>
      </div>
    </main>
  );
}
