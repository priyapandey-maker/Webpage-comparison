import { useMemo, useState } from 'react';
import ComparisonHeader from '../components/ComparisonHeader';
import ChangeSummary from '../components/ChangeSummary';
import ChangeFilters from '../components/ChangeFilters';
import ChangeCard from '../components/ChangeCard';
import NlpSummaryPanel from '../components/NlpSummaryPanel';
import HistoricalSnapshotViewer from '../components/HistoricalSnapshotViewer';
import { calculateChangeCounts } from '../utils/summary';
import { generateChangeSummary } from '../utils/generateSummary';

export default function ResultsPage({ comparison, onCompareAnother }) {
  const [activeFilter, setActiveFilter] = useState('all');

  const changes = Array.isArray(comparison?.changes) ? comparison.changes : [];
  const hasWayback = Boolean(comparison?.waybackContext || comparison?.version1?.replayUrl || comparison?.version2?.replayUrl);
  const hasNlp = Boolean(comparison?.nlpAnalysis);

  let sectionCounter = 2;
  const waybackSectionNum = hasWayback ? `0${sectionCounter++}` : null;
  const nlpSectionNum = hasNlp ? `0${sectionCounter++}` : null;
  const changesSectionNum = `0${sectionCounter}`;

  const counts = useMemo(() => calculateChangeCounts(changes), [changes]);
  const summarySentences = useMemo(
    () => generateChangeSummary(changes, comparison?.nlpAnalysis),
    [changes, comparison?.nlpAnalysis],
  );
  const visibleChanges = useMemo(
    () => activeFilter === 'all'
      ? changes
      : changes.filter((change) => change.category === activeFilter),
    [activeFilter, changes],
  );

  const waybackContext = useMemo(() => {
    if (!hasWayback) return null;
    return {
      targetUrl: comparison.waybackContext?.targetUrl || comparison.version1?.originalUrl || comparison.version2?.originalUrl || '',
      version1: comparison.waybackContext?.version1 || comparison.version1,
      version2: comparison.waybackContext?.version2 || comparison.version2,
    };
  }, [hasWayback, comparison]);

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

        {hasWayback && waybackContext && (
          <HistoricalSnapshotViewer
            waybackContext={waybackContext}
            sectionNumber={waybackSectionNum}
          />
        )}

        {hasNlp && (
          <NlpSummaryPanel
            nlpAnalysis={comparison.nlpAnalysis}
            sectionNumber={nlpSectionNum}
          />
        )}

        <section className="changes-section" aria-labelledby="details-heading">
          <div className="section-heading details-heading">
            <div>
              <span className="section-number">{changesSectionNum}</span>
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
