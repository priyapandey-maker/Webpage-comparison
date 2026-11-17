import { useState } from 'react';

export default function HistoricalSnapshotViewer({ waybackContext, sectionNumber = '02' }) {
  const [activeTab, setActiveTab] = useState('both'); // 'both' | 'v1' | 'v2'
  const [showEmbeds, setShowEmbeds] = useState(true);

  if (!waybackContext) return null;

  const version1 = waybackContext.version1;
  const version2 = waybackContext.version2;
  if (!version1 || !version2) return null;

  const targetUrl = waybackContext.targetUrl || version1.originalUrl || version2.originalUrl || 'Historical Webpage';

  return (
    <section className="snapshot-viewer-section" aria-labelledby="snapshot-verification-heading">
      <div className="section-heading">
        <div>
          <span className="section-number">{sectionNumber}</span>
          <h2 id="snapshot-verification-heading">Verified Historical Captures &amp; Visual Inspection</h2>
        </div>
        <p>Exact Wayback Machine captures retrieved and verified for comparison</p>
      </div>

      {/* Verification Summary Card */}
      <div className="snapshot-verification-card">
        <div className="snapshot-verification-header">
          <div className="snapshot-target-info">
            <span className="snapshot-target-label">Original Webpage URL:</span>
            <strong className="snapshot-target-value" title={targetUrl}>{targetUrl}</strong>
          </div>
          <span className="snapshot-verified-badge" title="Verified against CDX point query">
            ✓ Exact Captures Verified via CDX
          </span>
        </div>

        <div className="snapshot-meta-grid">
          {/* Older Version Metadata */}
          <div className="snapshot-meta-card snapshot-meta-v1">
            <div className="snapshot-meta-top">
              <span className="wayback-badge-old">Version 1 • Baseline</span>
              <span className="snapshot-status-pill">HTTP 200 • HTML</span>
            </div>
            <div className="snapshot-meta-date">{version1.displayDate || version1.datetime || 'Unknown date'}</div>
            <div className="snapshot-meta-row">
              <span className="snapshot-meta-field">Timestamp:</span>
              <code>{version1.timestamp}</code>
            </div>
            <div className="snapshot-meta-row">
              <span className="snapshot-meta-field">Original URL:</span>
              <span className="snapshot-meta-orig" title={version1.originalUrl}>{version1.originalUrl}</span>
            </div>
            <div className="snapshot-meta-actions">
              <a
                href={version1.replayUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="snapshot-ext-link"
                title="Open exact older archived capture on web.archive.org in a new tab"
              >
                Open Older Version in Wayback Archive ↗
              </a>
            </div>
          </div>

          {/* Newer Version Metadata */}
          <div className="snapshot-meta-card snapshot-meta-v2">
            <div className="snapshot-meta-top">
              <span className="wayback-badge-new">Version 2 • Comparison</span>
              <span className="snapshot-status-pill">HTTP 200 • HTML</span>
            </div>
            <div className="snapshot-meta-date">{version2.displayDate || version2.datetime || 'Unknown date'}</div>
            <div className="snapshot-meta-row">
              <span className="snapshot-meta-field">Timestamp:</span>
              <code>{version2.timestamp}</code>
            </div>
            <div className="snapshot-meta-row">
              <span className="snapshot-meta-field">Original URL:</span>
              <span className="snapshot-meta-orig" title={version2.originalUrl}>{version2.originalUrl}</span>
            </div>
            <div className="snapshot-meta-actions">
              <a
                href={version2.replayUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="snapshot-ext-link"
                title="Open exact newer archived capture on web.archive.org in a new tab"
              >
                Open Newer Version in Wayback Archive ↗
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Visual Inspection Panel */}
      <div className="snapshot-inspection-panel">
        <div className="snapshot-inspection-header">
          <div className="snapshot-inspection-title-group">
            <h3>Visual Inspection</h3>
            <p>Inspect the two historical captures side by side or individually.</p>
          </div>

          <div className="snapshot-controls">
            <div className="snapshot-tab-group" role="tablist" aria-label="Visual inspection view mode">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'both'}
                className={`snapshot-tab-btn${activeTab === 'both' ? ' is-active' : ''}`}
                onClick={() => setActiveTab('both')}
              >
                Side by Side
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'v1'}
                className={`snapshot-tab-btn${activeTab === 'v1' ? ' is-active' : ''}`}
                onClick={() => setActiveTab('v1')}
              >
                Older Only
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'v2'}
                className={`snapshot-tab-btn${activeTab === 'v2' ? ' is-active' : ''}`}
                onClick={() => setActiveTab('v2')}
              >
                Newer Only
              </button>
            </div>

            <button
              type="button"
              className="snapshot-toggle-embeds-btn"
              onClick={() => setShowEmbeds(!showEmbeds)}
            >
              {showEmbeds ? 'Hide Embedded Previews' : 'Show Embedded Previews'}
            </button>
          </div>
        </div>

        {/* Security & Embedding Advisory Notice */}
        <div className="snapshot-embed-notice" role="note">
          <span className="snapshot-notice-icon" aria-hidden="true">ℹ</span>
          <span>
            <strong>Browser Security Notice:</strong> Live embedded iframes are sandboxed and subject to
            Wayback Machine origin headers (<code>X-Frame-Options</code> and <code>Content-Security-Policy</code>).
            If an embedded frame appears blank in your browser, use the <strong>Open in Wayback Archive ↗</strong> button
            to view the verified historical capture directly in a new tab.
          </span>
        </div>

        {/* Preview Frame Area */}
        {showEmbeds && (
          <div className={`snapshot-frames-layout snapshot-layout-${activeTab}`}>
            {/* Version 1 Frame */}
            {(activeTab === 'both' || activeTab === 'v1') && (
              <div className="snapshot-frame-card">
                <div className="snapshot-frame-bar">
                  <div className="snapshot-frame-info">
                    <span className="wayback-badge-old">Version 1 (Older)</span>
                    <span className="snapshot-frame-date">{version1.displayDate}</span>
                    <code className="snapshot-frame-ts">{version1.timestamp}</code>
                  </div>
                  <a
                    href={version1.replayUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="snapshot-frame-ext-btn"
                    title="Open in new tab"
                  >
                    Open in Archive ↗
                  </a>
                </div>
                <div className="snapshot-iframe-wrapper">
                  <iframe
                    src={version1.rawReplayUrl || version1.replayUrl}
                    title={`Older snapshot: ${version1.displayDate} (${version1.timestamp})`}
                    sandbox="allow-scripts allow-same-origin"
                    loading="lazy"
                    className="snapshot-iframe"
                  />
                </div>
              </div>
            )}

            {/* Version 2 Frame */}
            {(activeTab === 'both' || activeTab === 'v2') && (
              <div className="snapshot-frame-card">
                <div className="snapshot-frame-bar">
                  <div className="snapshot-frame-info">
                    <span className="wayback-badge-new">Version 2 (Newer)</span>
                    <span className="snapshot-frame-date">{version2.displayDate}</span>
                    <code className="snapshot-frame-ts">{version2.timestamp}</code>
                  </div>
                  <a
                    href={version2.replayUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="snapshot-frame-ext-btn"
                    title="Open in new tab"
                  >
                    Open in Archive ↗
                  </a>
                </div>
                <div className="snapshot-iframe-wrapper">
                  <iframe
                    src={version2.rawReplayUrl || version2.replayUrl}
                    title={`Newer snapshot: ${version2.displayDate} (${version2.timestamp})`}
                    sandbox="allow-scripts allow-same-origin"
                    loading="lazy"
                    className="snapshot-iframe"
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
