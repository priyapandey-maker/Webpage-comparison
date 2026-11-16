import { useState } from 'react';
import ResultsPage from './pages/ResultsPage';
import UploadPage from './pages/UploadPage';
import { compareFiles } from './services/comparisonService';

export default function App() {
  const [comparison, setComparison] = useState(null);

  async function handleCompare(version1File, version2File) {
    // Integration boundary: comparisonService sends both File objects to the
    // local Python API and returns the adapter's ResultsPage-ready JSON.
    const result = await compareFiles(version1File, version2File);
    setComparison(result);
  }

  function handleReset() {
    setComparison(null);
  }

  return comparison
    ? <ResultsPage comparison={comparison} onCompareAnother={handleReset} />
    : <UploadPage onCompare={handleCompare} />;
}
