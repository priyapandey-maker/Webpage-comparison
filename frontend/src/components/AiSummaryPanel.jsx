import { useCallback, useMemo } from 'react';
import { buildTopicGroups, sanitizeKeyTakeaway } from '../utils/changeGrouping';
import { getAiStatusInfo } from '../utils/aiStatus';

const SIGNIFICANCE_LABELS = {
  high: 'High Impact',
  medium: 'Moderate Impact',
  low: 'Low Impact',
};

export default function AiSummaryPanel({
  changes = [],
  aiSummary,
  aiStatus = null,
  sectionNumber = '02',
  onSelectChangeId,
  onNavigate,
  summarySentences = [],
  counts = {},
}) {
  const statusInfo = useMemo(() => getAiStatusInfo(aiStatus), [aiStatus]);

  const handleJumpToChange = useCallback((changeId) => {
    if (!changeId) return;
    if (typeof onSelectChangeId === 'function') {
      onSelectChangeId(changeId);
      return;
    }
    const targetEl = document.getElementById(`change-${changeId}`);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      targetEl.classList.remove('change-card-highlighted');
      void targetEl.offsetWidth;
      targetEl.classList.add('change-card-highlighted');
      setTimeout(() => {
        targetEl.classList.remove('change-card-highlighted');
      }, 2500);
    }
  }, [onSelectChangeId]);

  // Fallback state when AI summary is null, disabled, or unavailable
  if (!aiSummary || typeof aiSummary !== 'object' || !aiSummary.executive_summary) {
    return (
      <section className="ai-summary-section" aria-labelledby="ai-summary-heading">
        <div className="section-heading">
          <div>
            <span className="section-number">{sectionNumber}</span>
            <div className="ai-title-row">
              <h2 id="ai-summary-heading">AI Executive Summary</h2>
              <span className="ai-model-pill fallback-pill" title={statusInfo.title}>
                {statusInfo.pill}
              </span>
            </div>
          </div>
          <p className="ai-scope-reminder">
            Deterministic change information is displayed below in place of the local model summary.
          </p>
        </div>

        <div className="ai-fallback-card">
          <div className="fallback-header">
            <span className="fallback-icon" aria-hidden="true">ℹ</span>
            <div>
              <h3 className="fallback-title">{statusInfo.title}</h3>
              <p className="fallback-desc">{statusInfo.desc}</p>
            </div>
          </div>

          {Array.isArray(summarySentences) && summarySentences.length > 0 && (
            <div className="fallback-summary-content">
              <h4>Meaningful Change Breakdown</h4>
              {summarySentences.map((sentence, idx) => (
                <p key={idx} className="fallback-sentence">{sentence}</p>
              ))}
            </div>
          )}

          {typeof onNavigate === 'function' && (
            <div className="fallback-actions">
              <button
                type="button"
                className="primary-cta-btn"
                onClick={() => onNavigate('explorer')}
              >
                Inspect All {counts.total != null ? counts.total.toLocaleString() : ''} Changes in Explorer →
              </button>
            </div>
          )}
        </div>
      </section>
    );
  }

  const executiveSummary = String(aiSummary.executive_summary || '').trim();
  const keyTakeaways = useMemo(() => {
    if (!Array.isArray(aiSummary?.key_takeaways)) return [];
    return aiSummary.key_takeaways
      .map((t) => sanitizeKeyTakeaway(String(t).trim()))
      .filter(Boolean);
  }, [aiSummary?.key_takeaways]);

  // Normalized topic groups: 100% change ID representation, 0 duplicates, no unknown IDs, and no empty groups
  const topicGroups = useMemo(() => {
    const rawGroups = buildTopicGroups(changes, aiSummary);
    return rawGroups.filter((g) => {
      const ids = Array.isArray(g.changeIds)
        ? g.changeIds
        : Array.isArray(g.change_ids)
        ? g.change_ids
        : [];
      return ids.length > 0;
    });
  }, [changes, aiSummary]);

  const MAX_DISPLAY_CHIPS = 24;

  return (
    <section className="ai-summary-section" aria-labelledby="ai-summary-heading">
      <div className="section-heading">
        <div>
          <span className="section-number">{sectionNumber}</span>
          <div className="ai-title-row">
            <h2 id="ai-summary-heading">AI Executive Summary</h2>
            <span className="ai-model-pill" title="Synthesized locally using Qwen 2.5 1.5B via Ollama">
              Local LLM
            </span>
          </div>
        </div>
        <p className="ai-scope-reminder">
          Narrative explanation and thematic groupings grounded in detected structural changes.
        </p>
      </div>

      <div className="ai-overview-card">
        <div className="ai-card-header">
          <span className="ai-subheading-eyebrow">Overview</span>
          <h3 className="ai-subheading">Executive Summary</h3>
        </div>
        <p className="ai-executive-text">{executiveSummary}</p>
      </div>

      {keyTakeaways.length > 0 && (
        <div className="ai-takeaways-card">
          <div className="ai-card-header">
            <span className="ai-subheading-eyebrow">Highlights</span>
            <h3 className="ai-subheading">Key Takeaways</h3>
          </div>
          <ul className="ai-takeaways-list" aria-label="Key takeaways">
            {keyTakeaways.map((takeaway, idx) => (
              <li key={idx} className="ai-takeaway-item">
                <span className="ai-takeaway-icon" aria-hidden="true">✓</span>
                <span className="ai-takeaway-text">{takeaway}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {topicGroups.length > 0 && (
        <div className="ai-topics-wrapper">
          <div className="ai-topics-header">
            <h3 className="ai-subheading">Thematic Topic Groups</h3>
            <span className="ai-topics-hint">Click a change badge to navigate directly to it in Change Explorer</span>
          </div>

          <div className="ai-topics-grid">
            {topicGroups.map((group, idx) => {
              const sigKey = (group.significance || 'medium').toLowerCase();
              const sigLabel = SIGNIFICANCE_LABELS[sigKey] || SIGNIFICANCE_LABELS.medium;
              const changeIds = Array.isArray(group.changeIds)
                ? group.changeIds
                : Array.isArray(group.change_ids)
                ? group.change_ids
                : [];

              return (
                <article key={`${group.topic}-${idx}`} className={`ai-topic-card ai-topic-sig-${sigKey}`}>
                  <div className="ai-topic-topbar">
                    <h4 className="ai-topic-title">{group.topic}</h4>
                    <span className={`ai-sig-badge ai-sig-${sigKey}`}>{sigLabel}</span>
                  </div>

                  <p className="ai-topic-description">{group.description}</p>

                  {changeIds.length > 0 && (
                    <div className="ai-topic-changes">
                      <span className="ai-topic-changes-label">Supporting changes ({changeIds.length}):</span>
                      <div className="ai-chips-list">
                        {changeIds.slice(0, MAX_DISPLAY_CHIPS).map((cid) => (
                          <button
                            type="button"
                            key={cid}
                            className="ai-change-chip-btn"
                            onClick={() => handleJumpToChange(cid)}
                            title={`Jump to change #${cid} in Change Explorer`}
                            aria-label={`Jump to change item ${cid}`}
                          >
                            #{cid}
                          </button>
                        ))}
                        {changeIds.length > MAX_DISPLAY_CHIPS && (
                          <button
                            type="button"
                            className="ai-chip-more-btn"
                            onClick={() => handleJumpToChange(changeIds[MAX_DISPLAY_CHIPS] || changeIds[0])}
                            title={`Inspect remaining ${changeIds.length - MAX_DISPLAY_CHIPS} changes in Change Explorer`}
                            aria-label={`Inspect remaining ${changeIds.length - MAX_DISPLAY_CHIPS} changes in Change Explorer`}
                          >
                            +{changeIds.length - MAX_DISPLAY_CHIPS} more in Explorer →
                          </button>
                        )}
                      </div>
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
