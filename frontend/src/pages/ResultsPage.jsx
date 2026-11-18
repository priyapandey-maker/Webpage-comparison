import { useState, useMemo, useCallback } from 'react';
import NavigationSidebar from '../components/NavigationSidebar';
import OverviewSection from '../components/OverviewSection';
import AiSummaryPanel from '../components/AiSummaryPanel';
import ChangeExplorer from '../components/ChangeExplorer';
import NlpSummaryPanel from '../components/NlpSummaryPanel';
import HistoricalSnapshotViewer from '../components/HistoricalSnapshotViewer';
import TechnicalDetailsSection from '../components/TechnicalDetailsSection';
import { calculateChangeCounts } from '../utils/summary';
import { generateChangeSummary } from '../utils/generateSummary';
import { buildTopicGroups } from '../utils/changeGrouping';

export default function ResultsPage({ comparison, onCompareAnother }) {
  // 1. Navigation State: 'overview' by default
  const [activeSection, setActiveSection] = useState('overview');
  const [targetChangeId, setTargetChangeId] = useState(null);

  // 2. Data Extraction
  const changes = useMemo(() => {
    return Array.isArray(comparison?.changes) ? comparison.changes : [];
  }, [comparison?.changes]);

  const hasWayback = Boolean(
    comparison?.waybackContext ||
    comparison?.version1?.replayUrl ||
    comparison?.version2?.replayUrl
  );

  const hasAiSummary = Boolean(
    comparison?.aiSummary &&
    typeof comparison.aiSummary === 'object' &&
    comparison.aiSummary.executive_summary
  );

  const hasNlp = Boolean(comparison?.nlpAnalysis);

  const normalizedTopicGroups = useMemo(() => {
    return buildTopicGroups(changes, comparison?.aiSummary);
  }, [changes, comparison?.aiSummary]);

  const topicCount = hasAiSummary ? normalizedTopicGroups.length : 0;

  const similarityScore = comparison?.nlpAnalysis?.overall?.average_semantic_similarity ?? null;

  // 3. Computed Summaries & Counts
  const counts = useMemo(() => calculateChangeCounts(changes), [changes]);
  const summarySentences = useMemo(
    () => generateChangeSummary(changes, comparison?.nlpAnalysis),
    [changes, comparison?.nlpAnalysis],
  );

  const waybackContext = useMemo(() => {
    if (!hasWayback) return null;
    return {
      targetUrl:
        comparison.waybackContext?.targetUrl ||
        comparison.version1?.originalUrl ||
        comparison.version2?.originalUrl ||
        '',
      version1: comparison.waybackContext?.version1 || comparison.version1,
      version2: comparison.waybackContext?.version2 || comparison.version2,
    };
  }, [hasWayback, comparison]);

  // Section numbers
  const sectionNumbers = useMemo(() => {
    if (hasWayback) {
      return {
        overview: '01',
        ai: '02',
        explorer: '03',
        semantic: '04',
        snapshots: '05',
        technical: '06',
      };
    }
    return {
      overview: '01',
      ai: '02',
      explorer: '03',
      semantic: '04',
      snapshots: null,
      technical: '05',
    };
  }, [hasWayback]);

  // 4. Navigation Handlers
  const handleSectionChange = useCallback((sectionId) => {
    setActiveSection(sectionId);
    // Scroll page smoothly to top of content area on navigation
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const handleSelectChangeId = useCallback((changeId) => {
    setTargetChangeId(changeId);
    setActiveSection('explorer');
  }, []);

  const handleClearTargetChangeId = useCallback(() => {
    setTargetChangeId(null);
  }, []);

  return (
    <main className="results-main">
      <div className="results-top-bar">
        <button className="back-button" type="button" onClick={onCompareAnother}>
          ← Compare another pair
        </button>
      </div>

      <div className="results-dashboard-shell">
        {/* Persistent Section Navigation Sidebar */}
        <NavigationSidebar
          activeSection={activeSection}
          onSectionChange={handleSectionChange}
          counts={counts}
          hasAiSummary={hasAiSummary}
          hasNlp={hasNlp}
          hasWayback={hasWayback}
          topicCount={topicCount}
          similarityScore={similarityScore}
        />

        {/* Content Area: Exactly ONE section visible at a time.
            State in ChangeExplorer, filters, search, and accordions are 100% preserved
            across tab switches via hidden attribute */}
        <div className="results-content-area">
          {/* Section 1: Overview */}
          <div
            className="results-section-pane"
            hidden={activeSection !== 'overview'}
            role="region"
            aria-labelledby="tab-overview"
          >
            <OverviewSection
              comparison={comparison}
              counts={counts}
              summarySentences={summarySentences}
              hasWayback={hasWayback}
              waybackContext={waybackContext}
              hasAiSummary={hasAiSummary}
              hasNlp={hasNlp}
              onNavigate={handleSectionChange}
            />
          </div>

          {/* Section 2: AI Summary */}
          <div
            className="results-section-pane"
            hidden={activeSection !== 'ai-summary'}
            role="region"
            aria-labelledby="tab-ai-summary"
          >
            <AiSummaryPanel
              changes={changes}
              aiSummary={comparison?.aiSummary}
              aiStatus={comparison?.aiStatus || comparison?.ai_status}
              sectionNumber={sectionNumbers.ai}
              onSelectChangeId={handleSelectChangeId}
              onNavigate={handleSectionChange}
              summarySentences={summarySentences}
              counts={counts}
            />
          </div>

          {/* Section 3: Change Explorer (Always mounted to preserve search, filter, pagination & expanded groups!) */}
          <div
            className="results-section-pane"
            hidden={activeSection !== 'explorer'}
            role="region"
            aria-labelledby="tab-explorer"
          >
            <ChangeExplorer
              changes={changes}
              aiSummary={comparison?.aiSummary}
              targetChangeId={targetChangeId}
              onClearTargetChangeId={handleClearTargetChangeId}
              sectionNumber={sectionNumbers.explorer}
            />
          </div>

          {/* Section 4: Semantic Analysis */}
          <div
            className="results-section-pane"
            hidden={activeSection !== 'semantic'}
            role="region"
            aria-labelledby="tab-semantic"
          >
            <NlpSummaryPanel
              nlpAnalysis={comparison?.nlpAnalysis}
              sectionNumber={sectionNumbers.semantic}
            />
          </div>

          {/* Section 5: Snapshots (Historical Webpage Comparison only) */}
          {hasWayback && waybackContext && (
            <div
              className="results-section-pane"
              hidden={activeSection !== 'snapshots'}
              role="region"
              aria-labelledby="tab-snapshots"
            >
              <HistoricalSnapshotViewer
                waybackContext={waybackContext}
                sectionNumber={sectionNumbers.snapshots}
              />
            </div>
          )}

          {/* Section 6: Technical Details */}
          <div
            className="results-section-pane"
            hidden={activeSection !== 'technical'}
            role="region"
            aria-labelledby="tab-technical"
          >
            <TechnicalDetailsSection
              comparison={comparison}
              counts={counts}
              sectionNumber={sectionNumbers.technical}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
