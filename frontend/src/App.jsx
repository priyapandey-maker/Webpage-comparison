import { useState } from 'react';
import ResultsPage from './pages/ResultsPage';
import UploadPage from './pages/UploadPage';
import { compareFiles, compareUrls, compareWaybackSnapshots } from './services/comparisonService';

export default function App() {
  const [comparison, setComparison] = useState(null);

  async function handleCompareFiles(version1File, version2File) {
    const result = await compareFiles(version1File, version2File);
    setComparison(result);
  }

  async function handleCompareUrls(url1, url2) {
    const result = await compareUrls(url1, url2);
    setComparison(result);
  }

  async function handleCompareWayback(url, timestamp1, timestamp2) {
    const result = await compareWaybackSnapshots(url, timestamp1, timestamp2);
    setComparison(result);
  }

  function handleReset() {
    setComparison(null);
  }

  return comparison ? (
    <ResultsPage comparison={comparison} onCompareAnother={handleReset} />
  ) : (
    <UploadPage
      onCompareFiles={handleCompareFiles}
      onCompareUrls={handleCompareUrls}
      onCompareWayback={handleCompareWayback}
      onCompare={handleCompareFiles}
    />
  );
}
