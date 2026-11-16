import { useEffect, useMemo, useRef, useState } from 'react';
import FileDropZone from '../components/FileDropZone';
import { getWaybackSnapshots } from '../services/comparisonService';

function validateUrlInput(urlString) {
  const trimmed = (urlString || '').trim();
  if (!trimmed) {
    return { isValid: false, error: 'Please enter a webpage URL.' };
  }

  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return {
      isValid: false,
      error: 'Please enter a valid URL (e.g., https://example.com).',
    };
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return {
      isValid: false,
      error: 'Only HTTP and HTTPS URLs are supported.',
    };
  }

  if (!parsed.hostname) {
    return {
      isValid: false,
      error: 'The URL must include a valid hostname.',
    };
  }

  if (parsed.username || parsed.password) {
    return {
      isValid: false,
      error: 'Embedded credentials (username/password) are not permitted in URLs.',
    };
  }

  return { isValid: true, error: '', url: trimmed };
}

function validateYearInput(yearStr, label = 'Year') {
  if (!yearStr || !String(yearStr).trim()) {
    return { isValid: true, year: null, error: '' };
  }
  const trimmed = String(yearStr).trim();
  const num = Number(trimmed);
  if (!/^\d{4}$/.test(trimmed) || !Number.isInteger(num)) {
    return { isValid: false, year: null, error: `${label} must be a 4-digit number (e.g., 2005).` };
  }
  if (num < 1996 || num > 2099) {
    return { isValid: false, year: null, error: `${label} must be between 1996 and 2099.` };
  }
  return { isValid: true, year: num, error: '' };
}

export default function UploadPage({ onCompare, onCompareFiles, onCompareUrls, onCompareWayback }) {
  const [mode, setMode] = useState('files'); // 'files' | 'urls' | 'wayback'

  // File mode states
  const [version1File, setVersion1File] = useState(null);
  const [version2File, setVersion2File] = useState(null);

  // URL mode states
  const [url1, setUrl1] = useState('');
  const [url2, setUrl2] = useState('');
  const [url1Error, setUrl1Error] = useState('');
  const [url2Error, setUrl2Error] = useState('');

  // Wayback mode states
  const [waybackUrl, setWaybackUrl] = useState('');
  const [fromYear, setFromYear] = useState('');
  const [toYear, setToYear] = useState('');
  const [waybackUrlError, setWaybackUrlError] = useState('');
  const [yearRangeError, setYearRangeError] = useState('');
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryAttempted, setDiscoveryAttempted] = useState(false);
  const [discoveredSnapshots, setDiscoveredSnapshots] = useState([]);
  const [discoveredTotal, setDiscoveredTotal] = useState(0);
  const [isLimited, setIsLimited] = useState(false);
  const [discoveredUrl, setDiscoveredUrl] = useState('');
  const [discoveredFromYear, setDiscoveredFromYear] = useState('');
  const [discoveredToYear, setDiscoveredToYear] = useState('');
  const [selectedTimestamp1, setSelectedTimestamp1] = useState('');
  const [selectedTimestamp2, setSelectedTimestamp2] = useState('');

  const discoveryAbortControllerRef = useRef(null);
  const discoverySeqRef = useRef(0);

  // General execution states
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const isSubmittingRef = useRef(false);

  useEffect(() => {
    return () => {
      discoverySeqRef.current += 1;
      if (discoveryAbortControllerRef.current) {
        discoveryAbortControllerRef.current.abort();
        discoveryAbortControllerRef.current = null;
      }
    };
  }, []);

  function invalidateWaybackDiscovery() {
    discoverySeqRef.current += 1;
    if (discoveryAbortControllerRef.current) {
      discoveryAbortControllerRef.current.abort();
      discoveryAbortControllerRef.current = null;
    }
    setIsDiscovering(false);
    setDiscoveryAttempted(false);
    setDiscoveredSnapshots([]);
    setDiscoveredTotal(0);
    setIsLimited(false);
    setDiscoveredUrl('');
    setDiscoveredFromYear('');
    setDiscoveredToYear('');
    setSelectedTimestamp1('');
    setSelectedTimestamp2('');
  }

  function handleModeChange(nextMode) {
    if (isLoading || isSubmittingRef.current || isDiscovering) return;
    setMode(nextMode);
    setError('');
  }

  function handleUrl1Change(value) {
    setUrl1(value);
    if (url1Error) setUrl1Error('');
    if (error) setError('');
  }

  function handleUrl2Change(value) {
    setUrl2(value);
    if (url2Error) setUrl2Error('');
    if (error) setError('');
  }

  function handleWaybackUrlChange(value) {
    setWaybackUrl(value);
    if (waybackUrlError) setWaybackUrlError('');
    if (error) setError('');
    invalidateWaybackDiscovery();
  }

  function handleFromYearChange(value) {
    setFromYear(value);
    if (yearRangeError) setYearRangeError('');
    if (error) setError('');
    invalidateWaybackDiscovery();
  }

  function handleToYearChange(value) {
    setToYear(value);
    if (yearRangeError) setYearRangeError('');
    if (error) setError('');
    invalidateWaybackDiscovery();
  }

  async function handleDiscoverSnapshots(e) {
    if (e) e.preventDefault();
    if (isLoading) return;

    setError('');
    const vResult = validateUrlInput(waybackUrl);
    setWaybackUrlError(vResult.error);

    const fromRes = validateYearInput(fromYear, 'From Year');
    const toRes = validateYearInput(toYear, 'To Year');

    if (!fromRes.isValid) {
      setYearRangeError(fromRes.error);
      return;
    }
    if (!toRes.isValid) {
      setYearRangeError(toRes.error);
      return;
    }
    if (fromRes.year != null && toRes.year != null && fromRes.year > toRes.year) {
      setYearRangeError(`From Year (${fromRes.year}) must be less than or equal to To Year (${toRes.year}).`);
      return;
    }
    setYearRangeError('');

    if (!vResult.isValid) {
      return;
    }

    discoverySeqRef.current += 1;
    const currentSeq = discoverySeqRef.current;

    if (discoveryAbortControllerRef.current) {
      discoveryAbortControllerRef.current.abort();
      discoveryAbortControllerRef.current = null;
    }
    const controller = new AbortController();
    discoveryAbortControllerRef.current = controller;

    setIsDiscovering(true);
    setDiscoveredSnapshots([]);
    setSelectedTimestamp1('');
    setSelectedTimestamp2('');
    setDiscoveryAttempted(false);

    try {
      const data = await getWaybackSnapshots(vResult.url, fromRes.year, toRes.year, {
        signal: controller.signal,
      });

      if (currentSeq !== discoverySeqRef.current) {
        return;
      }

      const snaps = Array.isArray(data?.snapshots) ? [...data.snapshots] : [];
      // Sort chronologically ascending
      snaps.sort((a, b) => a.timestamp.localeCompare(b.timestamp));

      setDiscoveredSnapshots(snaps);
      setDiscoveredTotal(data?.total_returned ?? snaps.length);
      setIsLimited(Boolean(data?.is_limited));
      setDiscoveredUrl(vResult.url);
      setDiscoveredFromYear(fromRes.year != null ? String(fromRes.year) : '');
      setDiscoveredToYear(toRes.year != null ? String(toRes.year) : '');
      setDiscoveryAttempted(true);

      if (snaps.length >= 2) {
        // Pre-select oldest for version 1, newest for version 2
        setSelectedTimestamp1(snaps[0].timestamp);
        setSelectedTimestamp2(snaps[snaps.length - 1].timestamp);
      } else {
        setSelectedTimestamp1('');
        setSelectedTimestamp2('');
      }
    } catch (err) {
      if (currentSeq !== discoverySeqRef.current || err.name === 'AbortError') {
        return;
      }
      setError(err.message || 'Failed to discover archived snapshots. Please try again.');
    } finally {
      if (currentSeq === discoverySeqRef.current) {
        setIsDiscovering(false);
        if (discoveryAbortControllerRef.current === controller) {
          discoveryAbortControllerRef.current = null;
        }
      }
    }
  }

  function handleResetDiscovery() {
    discoverySeqRef.current += 1;
    if (discoveryAbortControllerRef.current) {
      discoveryAbortControllerRef.current.abort();
      discoveryAbortControllerRef.current = null;
    }
    setIsDiscovering(false);
    setDiscoveryAttempted(false);
    setDiscoveredSnapshots([]);
    setDiscoveredTotal(0);
    setIsLimited(false);
    setDiscoveredUrl('');
    setDiscoveredFromYear('');
    setDiscoveredToYear('');
    setSelectedTimestamp1('');
    setSelectedTimestamp2('');
    setError('');
    setWaybackUrlError('');
    setYearRangeError('');
  }

  function handleSwapSnapshots() {
    const temp = selectedTimestamp1;
    setSelectedTimestamp1(selectedTimestamp2);
    setSelectedTimestamp2(temp);
    if (error) setError('');
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmittingRef.current || isLoading || isDiscovering) return;

    setError('');

    if (mode === 'files') {
      if (!version1File || !version2File) return;

      isSubmittingRef.current = true;
      setIsLoading(true);
      try {
        const handler = onCompareFiles || onCompare;
        if (handler) {
          await handler(version1File, version2File);
        }
      } catch (comparisonError) {
        setError(comparisonError.message || 'Comparison failed. Please check both HTML files and try again.');
      } finally {
        isSubmittingRef.current = false;
        setIsLoading(false);
      }
    } else if (mode === 'urls') {
      const v1Result = validateUrlInput(url1);
      const v2Result = validateUrlInput(url2);

      setUrl1Error(v1Result.error);
      setUrl2Error(v2Result.error);

      if (!v1Result.isValid || !v2Result.isValid) {
        setError('Please provide valid HTTP/HTTPS URLs for both webpages.');
        return;
      }

      isSubmittingRef.current = true;
      setIsLoading(true);
      try {
        const handler = onCompareUrls || onCompare;
        if (handler) {
          await handler(v1Result.url, v2Result.url);
        }
      } catch (comparisonError) {
        setError(comparisonError.message || 'Failed to compare live URLs. Please check the addresses and try again.');
      } finally {
        isSubmittingRef.current = false;
        setIsLoading(false);
      }
    } else if (mode === 'wayback') {
      const currentNormalizedUrl = waybackUrl.trim();
      const currentNormalizedFrom = String(fromYear || '').trim();
      const currentNormalizedTo = String(toYear || '').trim();

      const paramsMatch = Boolean(
        discoveryAttempted &&
        discoveredUrl &&
        discoveredUrl === currentNormalizedUrl &&
        String(discoveredFromYear || '').trim() === currentNormalizedFrom &&
        String(discoveredToYear || '').trim() === currentNormalizedTo,
      );

      // If discovery hasn't been run yet or search parameters changed, run discovery
      if (!paramsMatch || discoveredSnapshots.length < 2) {
        await handleDiscoverSnapshots();
        return;
      }

      if (!selectedTimestamp1 || !selectedTimestamp2) {
        setError('Please select two distinct historical snapshots to compare.');
        return;
      }

      if (selectedTimestamp1 === selectedTimestamp2) {
        setError('Selected timestamps must be different (cannot compare identical snapshots).');
        return;
      }

      isSubmittingRef.current = true;
      setIsLoading(true);
      try {
        if (onCompareWayback) {
          await onCompareWayback(discoveredUrl, selectedTimestamp1, selectedTimestamp2);
        }
      } catch (comparisonError) {
        setError(comparisonError.message || 'Failed to compare historical snapshots. Please try again.');
      } finally {
        isSubmittingRef.current = false;
        setIsLoading(false);
      }
    }
  }

  // Selected snapshot record lookup
  const selectedSnap1 = useMemo(
    () => discoveredSnapshots.find((s) => s.timestamp === selectedTimestamp1) || null,
    [discoveredSnapshots, selectedTimestamp1],
  );
  const selectedSnap2 = useMemo(
    () => discoveredSnapshots.find((s) => s.timestamp === selectedTimestamp2) || null,
    [discoveredSnapshots, selectedTimestamp2],
  );

  const currentNormalizedUrl = waybackUrl.trim();
  const currentNormalizedFrom = String(fromYear || '').trim();
  const currentNormalizedTo = String(toYear || '').trim();

  const isWaybackParamsMatch = Boolean(
    discoveryAttempted &&
    discoveredUrl &&
    discoveredUrl === currentNormalizedUrl &&
    String(discoveredFromYear || '').trim() === currentNormalizedFrom &&
    String(discoveredToYear || '').trim() === currentNormalizedTo,
  );

  const isFileReady = Boolean(version1File && version2File);
  const isUrlReady = Boolean(url1.trim() && url2.trim());
  const isWaybackReady = Boolean(
    isWaybackParamsMatch &&
    discoveredSnapshots.length >= 2 &&
    selectedTimestamp1 &&
    selectedTimestamp2 &&
    selectedTimestamp1 !== selectedTimestamp2,
  );

  let isSubmitDisabled = false;
  if (mode === 'files') {
    isSubmitDisabled = !isFileReady || isLoading;
  } else if (mode === 'urls') {
    isSubmitDisabled = !isUrlReady || isLoading;
  } else if (mode === 'wayback') {
    isSubmitDisabled = !isWaybackReady || isLoading || isDiscovering;
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
          <div className="mode-switcher" role="tablist" aria-label="Comparison input mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'files'}
              aria-controls="mode-panel-files"
              id="mode-tab-files"
              className={`mode-tab-button${mode === 'files' ? ' is-active' : ''}`}
              onClick={() => handleModeChange('files')}
              disabled={isLoading || isDiscovering}
            >
              Upload HTML Files
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'urls'}
              aria-controls="mode-panel-urls"
              id="mode-tab-urls"
              className={`mode-tab-button${mode === 'urls' ? ' is-active' : ''}`}
              onClick={() => handleModeChange('urls')}
              disabled={isLoading || isDiscovering}
            >
              Compare Live URLs
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'wayback'}
              aria-controls="mode-panel-wayback"
              id="mode-tab-wayback"
              className={`mode-tab-button${mode === 'wayback' ? ' is-active' : ''}`}
              onClick={() => handleModeChange('wayback')}
              disabled={isLoading || isDiscovering}
            >
              Compare Historical Versions
            </button>
          </div>

          <div className="upload-intro">
            <div>
              <span className="section-number">01</span>
              <h2>
                {mode === 'files' && 'Select webpage versions'}
                {mode === 'urls' && 'Enter webpage URLs'}
                {mode === 'wayback' && 'Explore & compare archived versions'}
              </h2>
            </div>
            <p>
              {mode === 'files' &&
                'Choose the older webpage first, followed by the newer version. Both files will be compared to identify structural and content changes.'}
              {mode === 'urls' &&
                'Enter the baseline webpage URL first, followed by the newer version. Both pages will be securely fetched and compared.'}
              {mode === 'wayback' &&
                'Search the Internet Archive Wayback Machine for historical captures of any webpage, then pick two distinct dates to compare.'}
            </p>
          </div>

          {/* Mode 1: Upload Files Panel */}
          {mode === 'files' && (
            <div
              id="mode-panel-files"
              role="tabpanel"
              aria-labelledby="mode-tab-files"
              className="upload-grid"
            >
              <FileDropZone
                id="version-1"
                label="Version 1"
                subtitle="Older webpage"
                file={version1File}
                onFileChange={(f) => {
                  setVersion1File(f);
                  if (error) setError('');
                }}
              />
              <FileDropZone
                id="version-2"
                label="Version 2"
                subtitle="Newer webpage"
                file={version2File}
                onFileChange={(f) => {
                  setVersion2File(f);
                  if (error) setError('');
                }}
              />
            </div>
          )}

          {/* Mode 2: Live URLs Panel */}
          {mode === 'urls' && (
            <div
              id="mode-panel-urls"
              role="tabpanel"
              aria-labelledby="mode-tab-urls"
              className="upload-grid"
            >
              <section className="upload-column" aria-labelledby="url-1-heading">
                <div className="upload-column-heading">
                  <span>Version 1</span>
                  <h2 id="url-1-heading">Older webpage URL</h2>
                </div>
                <div className="url-card">
                  <label htmlFor="url-1-input" className="url-input-label">
                    Baseline webpage address
                  </label>
                  <input
                    id="url-1-input"
                    type="url"
                    inputMode="url"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck="false"
                    className={`url-input${url1Error ? ' has-error' : ''}`}
                    placeholder="https://example.com/v1"
                    value={url1}
                    onChange={(e) => handleUrl1Change(e.target.value)}
                    disabled={isLoading}
                    aria-describedby={`url-1-help${url1Error ? ' url-1-error' : ''}`}
                    aria-invalid={Boolean(url1Error)}
                  />
                  <span id="url-1-help" className="url-help-text">
                    Must be a publicly accessible HTTP or HTTPS URL.
                  </span>
                  {url1Error && (
                    <p id="url-1-error" className="file-error url-field-error" role="alert">
                      {url1Error}
                    </p>
                  )}
                </div>
              </section>

              <section className="upload-column" aria-labelledby="url-2-heading">
                <div className="upload-column-heading">
                  <span>Version 2</span>
                  <h2 id="url-2-heading">Newer webpage URL</h2>
                </div>
                <div className="url-card">
                  <label htmlFor="url-2-input" className="url-input-label">
                    Newer webpage address
                  </label>
                  <input
                    id="url-2-input"
                    type="url"
                    inputMode="url"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck="false"
                    className={`url-input${url2Error ? ' has-error' : ''}`}
                    placeholder="https://example.com/v2"
                    value={url2}
                    onChange={(e) => handleUrl2Change(e.target.value)}
                    disabled={isLoading}
                    aria-describedby={`url-2-help${url2Error ? ' url-2-error' : ''}`}
                    aria-invalid={Boolean(url2Error)}
                  />
                  <span id="url-2-help" className="url-help-text">
                    Must be a publicly accessible HTTP or HTTPS URL.
                  </span>
                  {url2Error && (
                    <p id="url-2-error" className="file-error url-field-error" role="alert">
                      {url2Error}
                    </p>
                  )}
                </div>
              </section>
            </div>
          )}

          {/* Mode 3: Wayback Historical Comparison Panel */}
          {mode === 'wayback' && (
            <div
              id="mode-panel-wayback"
              role="tabpanel"
              aria-labelledby="mode-tab-wayback"
              className="wayback-panel"
            >
              {/* Step A: URL & Year Filter Bar */}
              <div className="wayback-search-card">
                <div className="wayback-search-row">
                  <div className="wayback-url-group">
                    <label htmlFor="wayback-url-input" className="url-input-label">
                      Target Webpage URL
                    </label>
                    <input
                      id="wayback-url-input"
                      type="url"
                      inputMode="url"
                      autoCapitalize="none"
                      autoCorrect="off"
                      spellCheck="false"
                      className={`url-input${waybackUrlError ? ' has-error' : ''}`}
                      placeholder="https://example.com"
                      value={waybackUrl}
                      onChange={(e) => handleWaybackUrlChange(e.target.value)}
                      disabled={isDiscovering || isLoading}
                      aria-describedby={`wayback-url-help${waybackUrlError ? ' wayback-url-error' : ''}`}
                      aria-invalid={Boolean(waybackUrlError)}
                    />
                    <span id="wayback-url-help" className="url-help-text">
                      Enter any webpage URL archived on web.archive.org.
                    </span>
                    {waybackUrlError && (
                      <p id="wayback-url-error" className="file-error url-field-error" role="alert">
                        {waybackUrlError}
                      </p>
                    )}
                  </div>

                  <div className="wayback-years-group">
                    <div className="wayback-year-item">
                      <label htmlFor="wayback-from-year" className="url-input-label">
                        From Year <span className="label-optional">(optional)</span>
                      </label>
                      <input
                        id="wayback-from-year"
                        type="number"
                        min="1996"
                        max="2099"
                        placeholder="e.g., 2000"
                        className="url-input wayback-year-input"
                        value={fromYear}
                        onChange={(e) => handleFromYearChange(e.target.value)}
                        disabled={isDiscovering || isLoading}
                      />
                    </div>

                    <div className="wayback-year-item">
                      <label htmlFor="wayback-to-year" className="url-input-label">
                        To Year <span className="label-optional">(optional)</span>
                      </label>
                      <input
                        id="wayback-to-year"
                        type="number"
                        min="1996"
                        max="2099"
                        placeholder="e.g., 2022"
                        className="url-input wayback-year-input"
                        value={toYear}
                        onChange={(e) => handleToYearChange(e.target.value)}
                        disabled={isDiscovering || isLoading}
                      />
                    </div>
                  </div>

                  <div className="wayback-search-action">
                    <button
                      type="button"
                      className="primary-button wayback-find-button"
                      onClick={handleDiscoverSnapshots}
                      disabled={isDiscovering || isLoading || !waybackUrl.trim()}
                    >
                      {isDiscovering ? 'Searching Wayback...' : 'Find Archived Versions'}
                    </button>
                  </div>
                </div>

                {yearRangeError && (
                  <p className="file-error wayback-year-error" role="alert">
                    {yearRangeError}
                  </p>
                )}
              </div>

              {/* Step B: Discovery Loading State */}
              {isDiscovering && (
                <div className="wayback-loading-card" role="status" aria-live="polite">
                  <div className="wayback-loading-spinner" aria-hidden="true" />
                  <div>
                    <strong>Querying the Wayback Machine CDX Index...</strong>
                    <p>Discovering available historical captures for {waybackUrl.trim()}.</p>
                  </div>
                </div>
              )}

              {/* Step C: Discovery Results & Snapshot Selectors */}
              {discoveryAttempted && !isDiscovering && isWaybackParamsMatch && (
                <div className="wayback-results-section">
                  {/* Discovery Status Banner */}
                  <div className="wayback-meta-banner">
                    <div className="wayback-meta-info">
                      <span className="wayback-count-badge">
                        {discoveredTotal} {discoveredTotal === 1 ? 'capture' : 'captures'} found
                      </span>
                      <span className="wayback-target-url" title={discoveredUrl}>
                        for <strong>{discoveredUrl}</strong>
                      </span>
                      {isLimited && (
                        <span className="wayback-limit-tag" title="Results capped to 50 snapshots">
                          Limited to 50 latest captures
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      className="text-button wayback-new-search-btn"
                      onClick={handleResetDiscovery}
                    >
                      Change search
                    </button>
                  </div>

                  {/* Empty States */}
                  {discoveredSnapshots.length === 0 && (
                    <div className="nlp-notice nlp-notice-warning wayback-notice" role="alert">
                      <strong>No snapshots found:</strong> No archived HTML captures exist for this URL
                      {fromYear || toYear ? ' within the specified year range' : ''}. Try removing or broadening the
                      year filter, or testing another address.
                    </div>
                  )}

                  {discoveredSnapshots.length === 1 && (
                    <div className="nlp-notice nlp-notice-warning wayback-notice" role="alert">
                      <strong>Only 1 snapshot found:</strong> Comparison requires at least two distinct historical
                      captures. Try widening your year range to find earlier or later archived versions.
                    </div>
                  )}

                  {/* Selection Grid for >= 2 Snapshots */}
                  {discoveredSnapshots.length >= 2 && (
                    <>
                      <div className="upload-grid wayback-selection-grid">
                        {/* Snapshot 1 Column */}
                        <section className="upload-column" aria-labelledby="snap-1-heading">
                          <div className="upload-column-heading">
                            <span>Version 1</span>
                            <h2 id="snap-1-heading">Older Historical Snapshot</h2>
                          </div>
                          <div className="url-card wayback-select-card">
                            <label htmlFor="snapshot-1-select" className="url-input-label">
                              Select Baseline Snapshot
                            </label>
                            <select
                              id="snapshot-1-select"
                              className="url-input wayback-select"
                              value={selectedTimestamp1}
                              onChange={(e) => {
                                setSelectedTimestamp1(e.target.value);
                                if (error) setError('');
                              }}
                              disabled={isLoading}
                              aria-describedby="snap-1-meta"
                            >
                              <option value="">-- Choose an archived date --</option>
                              {discoveredSnapshots.map((snap) => (
                                <option
                                  key={`snap1-${snap.timestamp}`}
                                  value={snap.timestamp}
                                  disabled={snap.timestamp === selectedTimestamp2}
                                >
                                  {snap.display_date} ({snap.timestamp})
                                </option>
                              ))}
                            </select>

                            {selectedSnap1 ? (
                              <div id="snap-1-meta" className="wayback-card-preview">
                                <div className="wayback-preview-header">
                                  <span className="wayback-badge-old">Older Capture</span>
                                  <span className="wayback-badge-code">HTTP 200 • HTML</span>
                                </div>
                                <div className="wayback-preview-date">{selectedSnap1.display_date}</div>
                                <div className="wayback-preview-row">
                                  <span className="preview-label">Timestamp:</span>
                                  <code>{selectedSnap1.timestamp}</code>
                                </div>
                                <div className="wayback-preview-row">
                                  <span className="preview-label">Archived URL:</span>
                                  <span className="preview-value" title={selectedSnap1.original_url}>
                                    {selectedSnap1.original_url}
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <p className="url-help-text" id="snap-1-meta">
                                Select an earlier snapshot from the dropdown above.
                              </p>
                            )}
                          </div>
                        </section>

                        {/* Snapshot 2 Column */}
                        <section className="upload-column" aria-labelledby="snap-2-heading">
                          <div className="upload-column-heading">
                            <span>Version 2</span>
                            <h2 id="snap-2-heading">Newer Historical Snapshot</h2>
                          </div>
                          <div className="url-card wayback-select-card">
                            <label htmlFor="snapshot-2-select" className="url-input-label">
                              Select Comparison Snapshot
                            </label>
                            <select
                              id="snapshot-2-select"
                              className="url-input wayback-select"
                              value={selectedTimestamp2}
                              onChange={(e) => {
                                setSelectedTimestamp2(e.target.value);
                                if (error) setError('');
                              }}
                              disabled={isLoading}
                              aria-describedby="snap-2-meta"
                            >
                              <option value="">-- Choose an archived date --</option>
                              {discoveredSnapshots.map((snap) => (
                                <option
                                  key={`snap2-${snap.timestamp}`}
                                  value={snap.timestamp}
                                  disabled={snap.timestamp === selectedTimestamp1}
                                >
                                  {snap.display_date} ({snap.timestamp})
                                </option>
                              ))}
                            </select>

                            {selectedSnap2 ? (
                              <div id="snap-2-meta" className="wayback-card-preview">
                                <div className="wayback-preview-header">
                                  <span className="wayback-badge-new">Newer Capture</span>
                                  <span className="wayback-badge-code">HTTP 200 • HTML</span>
                                </div>
                                <div className="wayback-preview-date">{selectedSnap2.display_date}</div>
                                <div className="wayback-preview-row">
                                  <span className="preview-label">Timestamp:</span>
                                  <code>{selectedSnap2.timestamp}</code>
                                </div>
                                <div className="wayback-preview-row">
                                  <span className="preview-label">Archived URL:</span>
                                  <span className="preview-value" title={selectedSnap2.original_url}>
                                    {selectedSnap2.original_url}
                                  </span>
                                </div>
                              </div>
                            ) : (
                              <p className="url-help-text" id="snap-2-meta">
                                Select a later snapshot from the dropdown above.
                              </p>
                            )}
                          </div>
                        </section>
                      </div>

                      {/* Swap Convenience Action */}
                      <div className="wayback-swap-container">
                        <button
                          type="button"
                          className="text-button wayback-swap-btn"
                          onClick={handleSwapSnapshots}
                          disabled={isLoading || !selectedTimestamp1 || !selectedTimestamp2}
                          title="Swap Version 1 and Version 2 selections"
                        >
                          ⇄ Swap Version 1 &amp; Version 2
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Bottom Compare Action Button */}
          <div className="compare-action">
            {error && <p className="file-error comparison-error" role="alert">{error}</p>}
            <button
              className="primary-button"
              type="submit"
              disabled={isSubmitDisabled}
            >
              {isLoading && (
                mode === 'files'
                  ? 'Preparing comparison results...'
                  : mode === 'urls'
                    ? 'Fetching and comparing webpages...'
                    : 'Retrieving archived captures & comparing...'
              )}
              {!isLoading && (
                mode === 'files'
                  ? 'Compare Versions'
                  : mode === 'urls'
                    ? 'Compare Live URLs'
                    : 'Compare Historical Versions'
              )}
            </button>
            <span className="loading-status" role="status" aria-live="polite">
              {isLoading && (
                mode === 'files'
                  ? 'Preparing comparison results...'
                  : mode === 'urls'
                    ? 'Fetching and comparing live webpages...'
                    : 'Retrieving raw captures from Wayback Machine and executing comparison engine...'
              )}
            </span>
          </div>
        </form>
      </div>
    </main>
  );
}
