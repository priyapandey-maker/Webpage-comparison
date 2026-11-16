const stats = [
  ['total', 'Total Changes'],
  ['added', 'Added'],
  ['removed', 'Removed'],
  ['modified', 'Modified'],
];

function CountLine({ label, counts }) {
  return (
    <p>
      <strong>{label}</strong>
      <span>Added: {counts.added ?? 0}</span>
      <span>Removed: {counts.removed ?? 0}</span>
      <span>Modified: {counts.modified ?? 0}</span>
    </p>
  );
}

export default function ChangeSummary({ counts, summarySentences, engineCounts }) {
  const hasEngineCounts = engineCounts && typeof engineCounts === 'object';

  return (
    <section aria-labelledby="summary-heading">
      <div className="section-heading">
        <div>
          <span className="section-number">01</span>
          <h2 id="summary-heading">Change overview</h2>
        </div>
      </div>

      <div className="stat-grid">
        {stats.map(([key, label]) => (
          <article className={`stat-card stat-${key}`} key={key}>
            <span>{label}</span>
            <strong>{counts[key]}</strong>
          </article>
        ))}
      </div>

      <div className="change-summary-panel" aria-labelledby="change-summary-heading">
        <h3 id="change-summary-heading">Change Summary</h3>
        <div>
          {summarySentences.map((sentence) => <p key={sentence}>{sentence}</p>)}
        </div>
      </div>

      {hasEngineCounts && (
        <details className="technical-details">
          <summary>Technical details</summary>
          <div>
            <CountLine label="Raw engine changes" counts={engineCounts} />
            <CountLine label="Displayed meaningful changes" counts={counts} />
          </div>
        </details>
      )}
    </section>
  );
}
