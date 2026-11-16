import { useState } from 'react';

const CATEGORY_LABELS = {
  identical: 'Identical (≥99.9%)',
  high: 'High Overlap (80–99%)',
  moderate: 'Moderate Shift (50–79%)',
  low: 'Substantial Shift (25–49%)',
  substantially_different: 'Different (<25%)',
};

const CATEGORY_SHORT = {
  identical: 'Identical',
  high: 'High',
  moderate: 'Moderate',
  low: 'Low',
  substantially_different: 'Different',
};

function formatSimilarity(score) {
  if (score == null || typeof score !== 'number' || isNaN(score)) {
    return 'Not available';
  }
  return `${(score * 100).toFixed(1)}%`;
}

function CategoryBadge({ category }) {
  const normCategory = (category || '').toLowerCase();
  const label = CATEGORY_SHORT[normCategory] || category || 'Modified';
  return (
    <span className={`nlp-cat-badge nlp-cat-${normCategory}`}>
      {label}
    </span>
  );
}

function KeywordTags({ keywords, tone, prefix = '' }) {
  if (!Array.isArray(keywords) || keywords.length === 0) {
    return <span className="nlp-empty-inline">None identified</span>;
  }
  return (
    <div className="nlp-keyword-tag-list">
      {keywords.map((kw, i) => (
        <span key={`${kw}-${i}`} className={`nlp-keyword-tag nlp-kw-${tone}`}>
          {prefix}{kw}
        </span>
      ))}
    </div>
  );
}

function EntityTags({ entities, tone }) {
  if (!Array.isArray(entities) || entities.length === 0) {
    return null;
  }
  return (
    <div className="nlp-entity-tag-list">
      {entities.map((ent, i) => (
        <span key={`${ent.text}-${i}`} className={`nlp-entity-tag nlp-ent-${tone}`}>
          <strong>{ent.text}</strong>
          {ent.label && <small>{ent.label}</small>}
        </span>
      ))}
    </div>
  );
}

export default function NlpSummaryPanel({ nlpAnalysis, sectionNumber = '02' }) {
  const [expandedId, setExpandedId] = useState(null);

  // 1. Guard against missing or malformed NLP analysis
  if (!nlpAnalysis || typeof nlpAnalysis !== 'object') {
    return null;
  }

  // 2. Handle NLP processing error response gracefully
  if (nlpAnalysis.status === 'failed' || nlpAnalysis.error) {
    return (
      <section className="nlp-section" aria-labelledby="nlp-summary-heading">
        <div className="section-heading">
          <div>
            <span className="section-number">{sectionNumber}</span>
            <h2 id="nlp-summary-heading">Semantic Analysis of Modified Text</h2>
          </div>
        </div>
        <div className="nlp-notice nlp-notice-warning" role="note">
          <strong>Semantic analysis note:</strong>{' '}
          {nlpAnalysis.error || 'NLP semantic analysis could not be completed for this comparison. Structural results are displayed below.'}
        </div>
      </section>
    );
  }

  const overall = nlpAnalysis.overall || {};
  const modifications = Array.isArray(nlpAnalysis.modifications) ? nlpAnalysis.modifications : [];
  const additions = Array.isArray(nlpAnalysis.additions) ? nlpAnalysis.additions : [];
  const removals = Array.isArray(nlpAnalysis.removals) ? nlpAnalysis.removals : [];

  const avgSimilarity = overall.average_semantic_similarity;
  const hasAvgSimilarity = avgSimilarity != null && typeof avgSimilarity === 'number';
  const distribution = overall.similarity_distribution || {};

  const topAddedKeywords = Array.isArray(overall.top_added_keywords) ? overall.top_added_keywords : [];
  const topRemovedKeywords = Array.isArray(overall.top_removed_keywords) ? overall.top_removed_keywords : [];

  const totalModifications = overall.total_modifications_analyzed ?? modifications.length;
  const totalAdditions = overall.total_additions_analyzed ?? additions.length;
  const totalRemovals = overall.total_removals_analyzed ?? removals.length;

  function toggleExpand(id) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  return (
    <section className="nlp-section" aria-labelledby="nlp-summary-heading">
      <div className="section-heading">
        <div>
          <span className="section-number">{sectionNumber}</span>
          <h2 id="nlp-summary-heading">Semantic Analysis of Modified Text</h2>
        </div>
        <p className="nlp-scope-reminder">
          Applies strictly to matched text modifications; does not reflect whole-webpage similarity.
        </p>
      </div>

      <div className="nlp-metrics-grid">
        {/* Main Metric: Average Semantic Similarity */}
        <article className="nlp-metric-card nlp-similarity-card">
          <span className="nlp-metric-label">Average Semantic Similarity</span>
          <strong className="nlp-similarity-value">
            {formatSimilarity(avgSimilarity)}
          </strong>
          <span className="nlp-metric-caption">
            {hasAvgSimilarity
              ? 'Mean cosine similarity across matched modified text items only'
              : 'No modified text items were available to measure'}
          </span>
        </article>

        {/* Count: Modifications Analyzed */}
        <article className="nlp-metric-card">
          <span className="nlp-metric-label">Modified Text Analyzed</span>
          <strong className="nlp-metric-count">{totalModifications}</strong>
          <span className="nlp-metric-caption">Text elements updated</span>
        </article>

        {/* Count: Additions Analyzed */}
        <article className="nlp-metric-card">
          <span className="nlp-metric-label">New Text Analyzed</span>
          <strong className="nlp-metric-count">{totalAdditions}</strong>
          <span className="nlp-metric-caption">Text elements added</span>
        </article>

        {/* Count: Removals Analyzed */}
        <article className="nlp-metric-card">
          <span className="nlp-metric-label">Removed Text Analyzed</span>
          <strong className="nlp-metric-count">{totalRemovals}</strong>
          <span className="nlp-metric-caption">Text elements removed</span>
        </article>
      </div>

      {/* Natural Language Summary from Backend */}
      {overall.summary && (
        <div className="nlp-summary-panel" aria-label="Semantic change summary">
          <h3 className="nlp-panel-title">Semantic Change Summary</h3>
          <p className="nlp-summary-text">{overall.summary}</p>
        </div>
      )}

      {/* Similarity Distribution Bar / Chips */}
      {totalModifications > 0 && (
        <div className="nlp-distribution-panel">
          <h3 className="nlp-panel-title">Similarity Distribution of Modified Text</h3>
          <div className="nlp-distribution-grid">
            {Object.entries(CATEGORY_LABELS).map(([catKey, label]) => {
              const count = distribution[catKey] ?? 0;
              return (
                <div key={catKey} className={`nlp-dist-card nlp-dist-${catKey}`}>
                  <span className="nlp-dist-label">{label}</span>
                  <strong className="nlp-dist-count">{count}</strong>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Top Keywords Insights */}
      {(topAddedKeywords.length > 0 || topRemovedKeywords.length > 0) && (
        <div className="nlp-keywords-panel">
          <h3 className="nlp-panel-title">Key Content Terms</h3>
          <div className="nlp-keywords-columns">
            {topAddedKeywords.length > 0 && (
              <div className="nlp-keyword-group">
                <span className="nlp-keyword-group-title">Key Added Terms</span>
                <KeywordTags keywords={topAddedKeywords} tone="added" prefix="+" />
              </div>
            )}
            {topRemovedKeywords.length > 0 && (
              <div className="nlp-keyword-group">
                <span className="nlp-keyword-group-title">Key Removed Terms</span>
                <KeywordTags keywords={topRemovedKeywords} tone="removed" prefix="-" />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Individual Modified Text Items Analysis */}
      {modifications.length > 0 && (
        <div className="nlp-modifications-list" aria-label="Individual modified text entries">
          <div className="nlp-modifications-header">
            <h3 className="nlp-panel-title">Modified Text Item Details ({modifications.length})</h3>
            <p>Inspect detailed semantic shifts, extracted keywords, and named entities for each modified text element.</p>
          </div>

          <div className="nlp-mod-items">
            {modifications.map((item, idx) => {
              const itemId = item.change_id ?? `nlp-mod-${idx}`;
              const isExpanded = expandedId === itemId;
              const hasSharedKw = Array.isArray(item.shared_keywords) && item.shared_keywords.length > 0;
              const hasAddedEnt = Array.isArray(item.added_entities) && item.added_entities.length > 0;
              const hasRemovedEnt = Array.isArray(item.removed_entities) && item.removed_entities.length > 0;

              return (
                <article key={itemId} className="nlp-mod-card">
                  <header
                    className="nlp-mod-header"
                    onClick={() => toggleExpand(itemId)}
                    role="button"
                    tabIndex={0}
                    aria-expanded={isExpanded}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        toggleExpand(itemId);
                      }
                    }}
                  >
                    <div className="nlp-mod-title-row">
                      <span className="nlp-mod-index">{String(idx + 1).padStart(2, '0')}</span>
                      <strong>{item.element || 'Modified Text'}</strong>
                    </div>

                    <div className="nlp-mod-score-row">
                      <span className="nlp-mod-score-text">
                        Similarity: <b>{formatSimilarity(item.similarity_score)}</b>
                      </span>
                      <CategoryBadge category={item.similarity_category} />
                      <span className="nlp-mod-chevron" aria-hidden="true">
                        {isExpanded ? '▲' : '▼'}
                      </span>
                    </div>
                  </header>

                  {item.explanation && (
                    <p className="nlp-mod-explanation">{item.explanation}</p>
                  )}

                  {isExpanded && (
                    <div className="nlp-mod-details">
                      {/* Before / After Text */}
                      <div className="nlp-mod-text-comparison">
                        <div className="nlp-text-block nlp-text-before">
                          <span className="nlp-text-label">Before</span>
                          <p>{item.original_text || <em className="nlp-empty-text">(empty)</em>}</p>
                        </div>
                        <span className="nlp-text-arrow" aria-hidden="true">→</span>
                        <div className="nlp-text-block nlp-text-after">
                          <span className="nlp-text-label">After</span>
                          <p>{item.updated_text || <em className="nlp-empty-text">(empty)</em>}</p>
                        </div>
                      </div>

                      {/* Keywords breakdown */}
                      <div className="nlp-mod-keywords-grid">
                        <div>
                          <span className="nlp-sublabel">Added Keywords</span>
                          <KeywordTags keywords={item.added_keywords} tone="added" prefix="+" />
                        </div>
                        <div>
                          <span className="nlp-sublabel">Removed Keywords</span>
                          <KeywordTags keywords={item.removed_keywords} tone="removed" prefix="-" />
                        </div>
                        {hasSharedKw && (
                          <div>
                            <span className="nlp-sublabel">Retained Keywords</span>
                            <KeywordTags keywords={item.shared_keywords} tone="shared" />
                          </div>
                        )}
                      </div>

                      {/* Named entities if present */}
                      {(hasAddedEnt || hasRemovedEnt) && (
                        <div className="nlp-mod-entities-grid">
                          {hasAddedEnt && (
                            <div>
                              <span className="nlp-sublabel">Added Entities</span>
                              <EntityTags entities={item.added_entities} tone="added" />
                            </div>
                          )}
                          {hasRemovedEnt && (
                            <div>
                              <span className="nlp-sublabel">Removed Entities</span>
                              <EntityTags entities={item.removed_entities} tone="removed" />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

