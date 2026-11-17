import { useCallback } from 'react';

const SIGNIFICANCE_LABELS = {
  high: 'High Impact',
  medium: 'Moderate Impact',
  low: 'Low Impact',
};

export default function AiSummaryPanel({ aiSummary, sectionNumber = '02' }) {
  // 1. Guard against missing, non-object, or empty AI summary
  if (!aiSummary || typeof aiSummary !== 'object' || !aiSummary.executive_summary) {
    return null;
  }

  const executiveSummary = String(aiSummary.executive_summary || '').trim();
  const keyTakeaways = Array.isArray(aiSummary.key_takeaways)
    ? aiSummary.key_takeaways.map((t) => String(t).trim()).filter(Boolean)
    : [];
  const topicGroups = Array.isArray(aiSummary.topic_groups)
    ? aiSummary.topic_groups.filter((g) => g && typeof g === 'object' && g.topic)
    : [];

  const handleJumpToChange = useCallback((changeId) => {
    if (!changeId) return;
    const targetEl = document.getElementById(`change-${changeId}`);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      targetEl.classList.remove('change-card-highlighted');
      // Trigger reflow to restart animation
      void targetEl.offsetWidth;
      targetEl.classList.add('change-card-highlighted');
      setTimeout(() => {
        targetEl.classList.remove('change-card-highlighted');
      }, 2500);
    }
  }, []);

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
            <span className="ai-topics-hint">Click a change badge to navigate to the change card</span>
          </div>

          <div className="ai-topics-grid">
            {topicGroups.map((group, idx) => {
              const sigKey = (group.significance || 'medium').toLowerCase();
              const sigLabel = SIGNIFICANCE_LABELS[sigKey] || SIGNIFICANCE_LABELS.medium;
              const changeIds = Array.isArray(group.change_ids) ? group.change_ids : [];

              return (
                <article key={`${group.topic}-${idx}`} className={`ai-topic-card ai-topic-sig-${sigKey}`}>
                  <div className="ai-topic-topbar">
                    <h4 className="ai-topic-title">{group.topic}</h4>
                    <span className={`ai-sig-badge ai-sig-${sigKey}`}>{sigLabel}</span>
                  </div>

                  <p className="ai-topic-description">{group.description}</p>

                  {changeIds.length > 0 && (
                    <div className="ai-topic-changes">
                      <span className="ai-topic-changes-label">Supporting changes:</span>
                      <div className="ai-chips-list">
                        {changeIds.map((cid) => (
                          <button
                            type="button"
                            key={cid}
                            className="ai-change-chip-btn"
                            onClick={() => handleJumpToChange(cid)}
                            title={`Jump to change #${cid}`}
                            aria-label={`Jump to change item ${cid}`}
                          >
                            #{cid}
                          </button>
                        ))}
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
