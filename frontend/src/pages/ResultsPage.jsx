import { useMemo, useState } from 'react';
import ComparisonHeader from '../components/ComparisonHeader';
import ChangeSummary from '../components/ChangeSummary';
import ChangeFilters from '../components/ChangeFilters';
import ChangeCard from '../components/ChangeCard';
import NlpSummaryPanel from '../components/NlpSummaryPanel';
import { calculateChangeCounts } from '../utils/summary';
import { generateChangeSummary } from '../utils/generateSummary';

export default function ResultsPage({ comparison, onCompareAnother }) {
  const [activeFilter, setActiveFilter] = useState('all');

  const changes = Array.isArray(comparison?.changes) ? comparison.changes : [];
  const hasNlp = Boolean(comparison?.nlpAnalysis);

  const counts = useMemo(() => calculateChangeCounts(changes), [changes]);
  const summarySentences = useMemo(() => generateChangeSummary(changes), [changes]);
  const visibleChanges = useMemo(
    () => activeFilter === 'all'
      ? changes
      : changes.filter((change) => change.category === activeFilter),
    [activeFilter, changes],
  );

  return (
    <main>
      <div className="dashboard-shell">
        <button className="back-button" type="button" onClick={onCompareAnother}>
          ← Compare another pair
        </button>
        <ComparisonHeader version1={comparison.version1} version2={comparison.version2} />
        <ChangeSummary
          counts={counts}
          summarySentences={summarySentences}
          engineCounts={comparison.engineSummary}
        />

        {hasNlp && (
          <NlpSummaryPanel
            nlpAnalysis={comparison.nlpAnalysis}
            sectionNumber="02"
          />
        )}

        <section className="changes-section" aria-labelledby="details-heading">
          <div className="section-heading details-heading">
            <div>
              <span className="section-number">{hasNlp ? '03' : '02'}</span>
              <h2 id="details-heading">Detected Changes</h2>
            </div>
            <p>Showing {visibleChanges.length} of {counts.total} changes</p>
          </div>

          <ChangeFilters
            activeFilter={activeFilter}
            onFilterChange={setActiveFilter}
            counts={counts}
          />

          <div className="change-list" aria-live="polite">
            {visibleChanges.map((change, index) => (
              <ChangeCard change={change} index={index} key={change.id} />
            ))}
            {visibleChanges.length === 0 && (
              <p className="empty-state">No changes match this filter.</p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
