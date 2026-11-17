import { useState } from 'react';
import ResultsPage from './pages/ResultsPage';
import UploadPage from './pages/UploadPage';
import { compareFiles, compareWaybackSnapshots } from './services/comparisonService';

export default function App() {
  const [comparison, setComparison] = useState(null);

  async function handleCompareFiles(version1File, version2File) {
    const result = await compareFiles(version1File, version2File);
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
      onCompareWayback={handleCompareWayback}
      onCompare={handleCompareFiles}
    />
  );
}
