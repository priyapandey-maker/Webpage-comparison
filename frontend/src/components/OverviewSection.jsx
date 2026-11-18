import ComparisonHeader from './ComparisonHeader';

const stats = [
  ['total', 'Total Changes'],
  ['added', 'Added'],
  ['removed', 'Removed'],
  ['modified', 'Modified'],
];

export default function OverviewSection({
  comparison,
  counts,
  summarySentences,
  hasWayback,
  waybackContext,
  hasAiSummary,
  hasNlp,
  onNavigate,
}) {
  const aiSummary = comparison?.aiSummary;
  const nlpAnalysis = comparison?.nlpAnalysis;

  const v1 = waybackContext?.version1;
  const v2 = waybackContext?.version2;
  const targetUrl = waybackContext?.targetUrl || comparison?.version1?.originalUrl || comparison?.version2?.originalUrl;

  return (
    <div className="section-panel overview-panel" id="section-overview" role="tabpanel" aria-labelledby="tab-overview">
      <ComparisonHeader version1={comparison.version1} version2={comparison.version2} />

      {/* Historical Snapshot Quick-Verification Card (Wayback Mode Only) */}
      {hasWayback && v1 && v2 && (
        <div className="overview-wayback-banner">
          <div className="wayback-banner-header">
            <div>
              <span className="overview-badge-tag">Historical Capture Verification</span>
              <h3 className="wayback-banner-url" title={targetUrl}>{targetUrl}</h3>
            </div>
            <span className="snapshot-verified-badge">✓ Exact Captures Verified via CDX</span>
          </div>

          <div className="wayback-banner-snapshots">
            <div className="wayback-snapshot-mini">
              <span className="wayback-mini-label">Baseline (Version 1):</span>
              <strong>{v1.displayDate || v1.datetime || v1.timestamp}</strong>
              <code>Timestamp: {v1.timestamp}</code>
            </div>
            <span className="wayback-mini-arrow" aria-hidden="true">→</span>
            <div className="wayback-snapshot-mini">
              <span className="wayback-mini-label">Comparison (Version 2):</span>
              <strong>{v2.displayDate || v2.datetime || v2.timestamp}</strong>
              <code>Timestamp: {v2.timestamp}</code>
            </div>
          </div>

          <div className="wayback-banner-actions">
            <button
              type="button"
              className="action-link-btn"
              onClick={() => onNavigate('snapshots')}
            >
              Inspect Archived Replays in Snapshots Section →
            </button>
          </div>
        </div>
      )}

      {/* Change Overview Stat Grid */}
      <div className="section-heading">
        <div>
          <span className="section-number">01</span>
          <h2>Change Overview</h2>
        </div>
        <p>Detected differences between older and newer webpage versions</p>
      </div>

      <div className="stat-grid">
        {stats.map(([key, label]) => (
          <article className={`stat-card stat-${key}`} key={key}>
            <span>{label}</span>
            <strong>{counts[key]?.toLocaleString?.() ?? counts[key]}</strong>
          </article>
        ))}
      </div>

      {/* Meaningful Change Summary Panel */}
      <div className="change-summary-panel" aria-labelledby="change-summary-heading">
        <h3 id="change-summary-heading">Meaningful Change Summary</h3>
        <div className="summary-sentences-list">
          {summarySentences.map((sentence, idx) => (
            <p key={idx} className={idx === 0 ? 'summary-lead-paragraph' : 'summary-detail-paragraph'}>
              {sentence}
            </p>
          ))}
        </div>
      </div>

      {/* Highlights & Previews for Other Sections */}
      <div className="overview-preview-grid">
        {hasAiSummary && aiSummary?.executive_summary && (
          <article className="preview-card preview-ai">
            <div className="preview-card-header">
              <span className="preview-tag tag-ai">AI Summary Preview</span>
              <h4>Executive Overview</h4>
            </div>
            <p className="preview-card-text">{aiSummary.executive_summary}</p>
            <button
              type="button"
              className="preview-jump-btn"
              onClick={() => onNavigate('ai-summary')}
            >
              View Full AI Breakdown &amp; Topic Groups →
            </button>
          </article>
        )}

        {hasNlp && nlpAnalysis && (
          <article className="preview-card preview-nlp">
            <div className="preview-card-header">
              <span className="preview-tag tag-nlp">Semantic Overview</span>
              <h4>
                Content Similarity:{' '}
                {typeof nlpAnalysis?.overall?.average_semantic_similarity === 'number' &&
                Number.isFinite(nlpAnalysis.overall.average_semantic_similarity)
                  ? `${(nlpAnalysis.overall.average_semantic_similarity * 100).toFixed(1)}%`
                  : 'N/A'}
              </h4>
            </div>
            <p className="preview-card-text">
              {nlpAnalysis.summary || 'Semantic analysis evaluated vocabulary overlap and content shifts between versions.'}
            </p>
            <button
              type="button"
              className="preview-jump-btn"
              onClick={() => onNavigate('semantic')}
            >
              View Semantic Analysis &amp; Keyword Shifts →
            </button>
          </article>
        )}
      </div>

      {/* Primary CTA to Explorer */}
      <div className="overview-cta-box">
        <div>
          <h3>Explore All {counts.total?.toLocaleString?.() ?? counts.total} Detected Changes</h3>
          <p>Filter by addition/removal/modification, search terms, and inspect before-and-after values.</p>
        </div>
        <button
          type="button"
          className="primary-cta-btn"
          onClick={() => onNavigate('explorer')}
        >
          Open Change Explorer →
        </button>
      </div>
    </div>
  );
}
