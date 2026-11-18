import { useMemo } from 'react';

export default function NavigationSidebar({
  activeSection,
  onSectionChange,
  counts,
  hasAiSummary,
  hasNlp,
  hasWayback,
  topicCount = 0,
  similarityScore = null,
}) {
  const navItems = useMemo(() => {
    let num = 1;
    const items = [
      {
        id: 'overview',
        label: 'Overview',
        number: `0${num++}`,
        badge: null,
        description: 'Comparison summary & stats',
      },
      {
        id: 'ai-summary',
        label: 'AI Summary',
        number: `0${num++}`,
        badge: hasAiSummary ? (topicCount > 0 ? `${topicCount} topics` : 'Ready') : 'Fallback',
        badgeType: hasAiSummary ? 'ai' : 'neutral',
        description: 'Executive briefing & groups',
      },
      {
        id: 'explorer',
        label: 'Change Explorer',
        number: `0${num++}`,
        badge: counts.total != null ? counts.total.toLocaleString() : null,
        badgeType: 'count',
        description: 'Interactive change details',
      },
      {
        id: 'semantic',
        label: 'Semantic Analysis',
        number: `0${num++}`,
        badge: similarityScore != null ? `${(similarityScore * 100).toFixed(0)}%` : (hasNlp ? 'NLP' : null),
        badgeType: 'nlp',
        description: 'Content shifts & terms',
      },
    ];

    if (hasWayback) {
      items.push({
        id: 'snapshots',
        label: 'Snapshots',
        number: `0${num++}`,
        badge: '2 verified',
        badgeType: 'wayback',
        description: 'Historical archive visualizer',
      });
    }

    items.push({
      id: 'technical',
      label: 'Technical Details',
      number: `0${num++}`,
      badge: null,
      description: 'Raw engine counts & metadata',
    });

    return items;
  }, [counts.total, hasAiSummary, hasNlp, hasWayback, topicCount, similarityScore]);

  return (
    <aside className="results-nav-sidebar" aria-label="Section Navigation">
      <div className="nav-sidebar-header">
        <span className="nav-sidebar-eyebrow">Navigation</span>
        <h3 className="nav-sidebar-title">Results Views</h3>
      </div>

      <nav className="nav-menu" role="tablist" aria-orientation="vertical">
        {navItems.map((item) => {
          const isActive = activeSection === item.id;
          return (
            <button
              key={item.id}
              role="tab"
              type="button"
              id={`tab-${item.id}`}
              aria-selected={isActive}
              aria-controls={`section-${item.id}`}
              className={`nav-item-btn ${isActive ? 'active' : ''}`}
              onClick={() => onSectionChange(item.id)}
            >
              <div className="nav-item-header">
                <span className="nav-item-number">{item.number}</span>
                <span className="nav-item-label">{item.label}</span>
                {item.badge && (
                  <span className={`nav-item-badge badge-${item.badgeType}`}>
                    {item.badge}
                  </span>
                )}
              </div>
              <span className="nav-item-description">{item.description}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
