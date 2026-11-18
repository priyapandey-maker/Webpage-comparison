export default function TechnicalDetailsSection({
  comparison,
  counts,
  sectionNumber = '06',
}) {
  const engineCounts = comparison?.engineSummary || {};
  const hasEngineCounts = Boolean(engineCounts && typeof engineCounts === 'object' && Object.keys(engineCounts).length > 0);
  const isWayback = Boolean(comparison?.waybackContext || comparison?.version1?.replayUrl);
  const hasAi = Boolean(comparison?.aiSummary);
  const hasNlp = Boolean(comparison?.nlpAnalysis);

  return (
    <section className="technical-details-section" id="section-technical" role="tabpanel" aria-labelledby="tab-technical">
      <div className="section-heading">
        <div>
          <span className="section-number">{sectionNumber}</span>
          <h2>Technical Details &amp; Diagnostics</h2>
        </div>
        <p>Engine statistics, metadata, and diagnostic payload inspection</p>
      </div>

      {/* Raw Engine vs Meaningful Counts */}
      <div className="tech-card">
        <h3 className="tech-card-title">Engine vs. Presentation Counts</h3>
        <p className="tech-card-desc">
          Comparison between raw DOM diffs detected by the underlying engine and user-facing meaningful presentation changes.
        </p>

        <div className="tech-counts-table-wrap">
          <table className="tech-counts-table">
            <thead>
              <tr>
                <th>Metric Category</th>
                <th>Raw Engine (DOM level)</th>
                <th>Presentation (Meaningful)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Total Changes</strong></td>
                <td><code>{engineCounts.total ?? '—'}</code></td>
                <td><strong className="text-total">{counts.total ?? 0}</strong></td>
              </tr>
              <tr>
                <td><strong>Additions</strong></td>
                <td><code>{engineCounts.added ?? '—'}</code></td>
                <td><span className="text-added">+{counts.added ?? 0}</span></td>
              </tr>
              <tr>
                <td><strong>Removals</strong></td>
                <td><code>{engineCounts.removed ?? '—'}</code></td>
                <td><span className="text-removed">−{counts.removed ?? 0}</span></td>
              </tr>
              <tr>
                <td><strong>Modifications</strong></td>
                <td><code>{engineCounts.modified ?? '—'}</code></td>
                <td><span className="text-modified">~{counts.modified ?? 0}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Execution Environment & Metadata */}
      <div className="tech-card">
        <h3 className="tech-card-title">Comparison Metadata &amp; Pipeline Status</h3>
        <dl className="tech-meta-list">
          <div className="tech-meta-item">
            <dt>Comparison Mode</dt>
            <dd>
              <span className={`tech-badge ${isWayback ? 'badge-wayback' : 'badge-file'}`}>
                {isWayback ? 'Historical Webpage Comparison (Wayback Machine)' : 'HTML File Comparison (Offline)'}
              </span>
            </dd>
          </div>

          <div className="tech-meta-item">
            <dt>Version 1 (Older)</dt>
            <dd>
              <strong>{comparison?.version1?.label || 'Version 1'}</strong>
              {comparison?.version1?.timestamp && <code>Timestamp: {comparison.version1.timestamp}</code>}
              {comparison?.version1?.originalUrl && <span className="tech-url">{comparison.version1.originalUrl}</span>}
            </dd>
          </div>

          <div className="tech-meta-item">
            <dt>Version 2 (Newer)</dt>
            <dd>
              <strong>{comparison?.version2?.label || 'Version 2'}</strong>
              {comparison?.version2?.timestamp && <code>Timestamp: {comparison.version2.timestamp}</code>}
              {comparison?.version2?.originalUrl && <span className="tech-url">{comparison.version2.originalUrl}</span>}
            </dd>
          </div>

          <div className="tech-meta-item">
            <dt>Semantic NLP Pipeline</dt>
            <dd>
              <span className={`tech-status-dot ${hasNlp ? 'dot-active' : 'dot-inactive'}`} />
              {hasNlp ? 'Active (TF-IDF & Semantic Classification attached)' : 'Not attached'}
            </dd>
          </div>

          <div className="tech-meta-item">
            <dt>AI Explanation Layer</dt>
            <dd>
              <span className={`tech-status-dot ${hasAi ? 'dot-active' : 'dot-inactive'}`} />
              {hasAi ? 'Active (Local Ollama qwen2.5:1.5b via CPU AVX2)' : 'Unavailable / Fallback'}
            </dd>
          </div>
        </dl>
      </div>

      {/* Collapsible Raw Engine Diagnostics */}
      {hasEngineCounts && (
        <details className="tech-details-accordion">
          <summary className="tech-accordion-summary">
            <span>View Raw Summary Diagnostics Object</span>
          </summary>
          <pre className="tech-json-preview">
            {JSON.stringify({
              engineSummary: comparison.engineSummary,
              presentationSummary: counts,
              waybackContext: comparison.waybackContext ? {
                targetUrl: comparison.waybackContext.targetUrl,
                version1Timestamp: comparison.waybackContext.version1?.timestamp,
                version2Timestamp: comparison.waybackContext.version2?.timestamp,
              } : null,
            }, null, 2)}
          </pre>
        </details>
      )}
    </section>
  );
}
