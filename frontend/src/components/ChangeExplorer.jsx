import { useState, useMemo, useEffect, useRef } from 'react';
import ChangeCard from './ChangeCard';
import { buildTopicGroups } from '../utils/changeGrouping';

const CATEGORY_OPTIONS = [
  { id: 'all', label: 'All Categories' },
  { id: 'added', label: 'Added' },
  { id: 'removed', label: 'Removed' },
  { id: 'modified', label: 'Modified' },
];

const SIGNIFICANCE_OPTIONS = [
  { id: 'all', label: 'All Significance' },
  { id: 'high', label: 'High Impact' },
  { id: 'medium', label: 'Moderate Impact' },
  { id: 'low', label: 'Low Impact' },
];

const PAGE_SIZE_OPTIONS = [20, 50, 100];

export default function ChangeExplorer({
  changes = [],
  aiSummary = null,
  targetChangeId = null,
  onClearTargetChangeId = null,
  sectionNumber = '03',
}) {
  // 1. Filter, Search & View States (Persistent within section mount)
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [activeTopic, setActiveTopic] = useState('all');
  const [activeSignificance, setActiveSignificance] = useState('all');
  const [viewMode, setViewMode] = useState('grouped'); // 'grouped' | 'flat'

  // 2. Pagination States
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);

  // 3. Topic Groups Generation (AI groups if available, deterministic fallback otherwise)
  const topicGroups = useMemo(() => {
    return buildTopicGroups(changes, aiSummary);
  }, [changes, aiSummary]);

  // Map each change ID to its assigned topic group info
  const changeIdToGroupMap = useMemo(() => {
    const map = new Map();
    for (const g of topicGroups) {
      for (const id of g.changeIds) {
        map.set(id, g);
      }
    }
    return map;
  }, [topicGroups]);

  // Expanded Groups state: defaults to all groups expanded
  const [expandedGroups, setExpandedGroups] = useState(() => {
    return new Set(topicGroups.map((g) => g.id));
  });

  // Keep expandedGroups synced when topicGroups change initially
  useEffect(() => {
    setExpandedGroups(new Set(topicGroups.map((g) => g.id)));
  }, [topicGroups]);

  // 4. Filtering & Search Logic
  const filteredChanges = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();

    return changes.filter((c) => {
      // Category filter
      if (activeCategory !== 'all' && c.category !== activeCategory) {
        return false;
      }

      const group = changeIdToGroupMap.get(c.id);

      // Topic filter
      if (activeTopic !== 'all' && group?.id !== activeTopic) {
        return false;
      }

      // Significance filter
      if (activeSignificance !== 'all') {
        const sig = group?.significance?.toLowerCase();
        if (sig !== activeSignificance) {
          return false;
        }
      }

      // Search Query filter
      if (q) {
        const desc = String(c.description || '').toLowerCase();
        const oldVal = String(c.oldValue || '').toLowerCase();
        const newVal = String(c.newValue || '').toLowerCase();
        const exp = String(c.explanation || '').toLowerCase();
        const elem = String(c.element || c.type || '').toLowerCase();
        const idStr = String(c.id);

        const matches =
          desc.includes(q) ||
          oldVal.includes(q) ||
          newVal.includes(q) ||
          exp.includes(q) ||
          elem.includes(q) ||
          idStr === q;

        if (!matches) return false;
      }

      return true;
    });
  }, [changes, searchQuery, activeCategory, activeTopic, activeSignificance, changeIdToGroupMap]);

  // Ref to prevent the filter-reset effect from resetting page to 1 during an intentional change jump
  const skipFilterResetRef = useRef(false);

  // Reset page to 1 whenever filters or search change manually
  const isFirstMount = useRef(true);
  useEffect(() => {
    if (isFirstMount.current) {
      isFirstMount.current = false;
      return;
    }
    if (skipFilterResetRef.current) {
      skipFilterResetRef.current = false;
      return;
    }
    setCurrentPage(1);
  }, [searchQuery, activeCategory, activeTopic, activeSignificance, pageSize]);

  // 5. Pagination Slicing (Performance: ONLY slice and render active page!)
  const totalMatching = filteredChanges.length;
  const totalPages = Math.max(1, Math.ceil(totalMatching / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);

  const startIndex = (safeCurrentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, totalMatching);
  const paginatedChanges = useMemo(() => {
    return filteredChanges.slice(startIndex, endIndex);
  }, [filteredChanges, startIndex, endIndex]);

  // Group the paginated slice for grouped rendering
  const paginatedGrouped = useMemo(() => {
    const map = new Map();
    for (const c of paginatedChanges) {
      const g = changeIdToGroupMap.get(c.id);
      const gid = g?.id || 'unassigned';
      if (!map.has(gid)) {
        map.set(gid, {
          group: g || {
            id: 'unassigned',
            topic: 'Additional Changes',
            description: 'Detected webpage changes.',
            significance: 'medium',
          },
          items: [],
        });
      }
      map.get(gid).items.push(c);
    }
    return Array.from(map.values());
  }, [paginatedChanges, changeIdToGroupMap]);

  // 6. Jump to Change ID handling (from AI Summary or deep link)
  useEffect(() => {
    if (targetChangeId == null) return;

    // Check if targetChangeId exists in changes
    const targetIdx = changes.findIndex((c) => c.id === targetChangeId);
    if (targetIdx === -1) {
      if (typeof onClearTargetChangeId === 'function') onClearTargetChangeId();
      return;
    }

    // Retrieve target group from existing changeIdToGroupMap
    const targetGroup = changeIdToGroupMap.get(targetChangeId);

    // If filters or search are active, reset them so targetChange is visible,
    // and tell the filter-reset effect to skip resetting to page 1
    const hasActiveFilters =
      searchQuery.trim() !== '' ||
      activeCategory !== 'all' ||
      activeTopic !== 'all' ||
      activeSignificance !== 'all';

    if (hasActiveFilters) {
      skipFilterResetRef.current = true;
      setActiveCategory('all');
      setActiveTopic('all');
      setActiveSignificance('all');
      setSearchQuery('');
    }

    // Expand the topic group containing targetChangeId
    if (targetGroup?.id) {
      setExpandedGroups((prev) => new Set([...prev, targetGroup.id]));
    }

    // Calculate the page index where targetChangeId falls in the full changes list
    const targetPage = Math.floor(targetIdx / pageSize) + 1;
    setCurrentPage(targetPage);

    // Scroll and highlight card once rendered
    const timer = setTimeout(() => {
      const targetEl = document.getElementById(`change-${targetChangeId}`);
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        targetEl.classList.remove('change-card-highlighted');
        void targetEl.offsetWidth;
        targetEl.classList.add('change-card-highlighted');
        setTimeout(() => {
          targetEl.classList.remove('change-card-highlighted');
        }, 3000);
      }
      skipFilterResetRef.current = false;
      if (typeof onClearTargetChangeId === 'function') {
        onClearTargetChangeId();
      }
    }, 150);

    return () => clearTimeout(timer);
  }, [targetChangeId, changes, pageSize, activeCategory, activeTopic, activeSignificance, searchQuery, changeIdToGroupMap, onClearTargetChangeId]);

  // Accordion Toggle Handlers
  function toggleGroup(groupId) {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  }

  function expandAll() {
    setExpandedGroups(new Set(topicGroups.map((g) => g.id)));
  }

  function collapseAll() {
    setExpandedGroups(new Set());
  }

  // Clear all filters
  function handleClearFilters() {
    setSearchQuery('');
    setActiveCategory('all');
    setActiveTopic('all');
    setActiveSignificance('all');
    setCurrentPage(1);
  }

  const hasActiveFilters =
    searchQuery.trim() !== '' ||
    activeCategory !== 'all' ||
    activeTopic !== 'all' ||
    activeSignificance !== 'all';

  return (
    <section className="change-explorer-section" id="section-explorer" role="tabpanel" aria-labelledby="tab-explorer">
      {/* Section Header */}
      <div className="section-heading explorer-header">
        <div>
          <span className="section-number">{sectionNumber}</span>
          <div className="explorer-title-row">
            <h2>Change Explorer</h2>
            <span className="explorer-count-badge">
              {totalMatching.toLocaleString()} {totalMatching === 1 ? 'change' : 'changes'}
            </span>
          </div>
        </div>
        <p>Interactive inspection, filtering, and search across all detected changes.</p>
      </div>

      {/* Control Bar: Search & View Switcher */}
      <div className="explorer-toolbar">
        <div className="search-input-wrap">
          <span className="search-icon" aria-hidden="true">🔍</span>
          <input
            type="search"
            className="explorer-search-input"
            placeholder="Search in descriptions, values, elements, or change #ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search detected changes"
          />
          {searchQuery && (
            <button
              type="button"
              className="search-clear-btn"
              onClick={() => setSearchQuery('')}
              title="Clear search query"
              aria-label="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        <div className="view-mode-toggle" role="group" aria-label="View layout mode">
          <button
            type="button"
            className={`toggle-btn ${viewMode === 'grouped' ? 'active' : ''}`}
            onClick={() => setViewMode('grouped')}
            aria-pressed={viewMode === 'grouped'}
          >
            Topic Accordions
          </button>
          <button
            type="button"
            className={`toggle-btn ${viewMode === 'flat' ? 'active' : ''}`}
            onClick={() => setViewMode('flat')}
            aria-pressed={viewMode === 'flat'}
          >
            Flat List
          </button>
        </div>
      </div>

      {/* Filter Row */}
      <div className="explorer-filter-bar">
        {/* Category Filter Pills */}
        <div className="filter-pill-group" role="group" aria-label="Filter by change category">
          {CATEGORY_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={`filter-pill ${activeCategory === opt.id ? 'active' : ''}`}
              onClick={() => setActiveCategory(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Dropdown Filters */}
        <div className="filter-dropdowns">
          {/* Topic Filter */}
          <div className="select-wrap">
            <label htmlFor="topic-filter-select" className="sr-only">Filter by topic group</label>
            <select
              id="topic-filter-select"
              className="explorer-select"
              value={activeTopic}
              onChange={(e) => setActiveTopic(e.target.value)}
            >
              <option value="all">All Topic Groups ({topicGroups.length})</option>
              {topicGroups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.topic} ({g.changes.length})
                </option>
              ))}
            </select>
          </div>

          {/* Significance Filter */}
          <div className="select-wrap">
            <label htmlFor="significance-filter-select" className="sr-only">Filter by significance</label>
            <select
              id="significance-filter-select"
              className="explorer-select"
              value={activeSignificance}
              onChange={(e) => setActiveSignificance(e.target.value)}
            >
              {SIGNIFICANCE_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Clear Filters Button */}
          {hasActiveFilters && (
            <button
              type="button"
              className="clear-filters-btn"
              onClick={handleClearFilters}
              title="Reset all search queries and filters"
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {/* Accordion Expand/Collapse All buttons (in grouped view) */}
      {viewMode === 'grouped' && (
        <div className="accordion-action-bar">
          <span className="results-range-indicator">
            Showing <strong>{totalMatching === 0 ? 0 : startIndex + 1}–{endIndex}</strong> of{' '}
            <strong>{totalMatching.toLocaleString()}</strong> matching changes
            {totalMatching !== changes.length && ` (filtered from ${changes.length.toLocaleString()} total)`}
          </span>
          <div className="accordion-btns">
            <button type="button" className="text-action-btn" onClick={expandAll}>
              Expand All
            </button>
            <span className="dot-sep">•</span>
            <button type="button" className="text-action-btn" onClick={collapseAll}>
              Collapse All
            </button>
          </div>
        </div>
      )}

      {/* Empty Search/Filter State */}
      {totalMatching === 0 && (
        <div className="explorer-empty-state">
          <p className="empty-title">No changes match the selected criteria.</p>
          <p className="empty-subtitle">Try adjusting your search terms or clearing active filters.</p>
          <button type="button" className="primary-cta-btn" onClick={handleClearFilters}>
            Clear All Filters
          </button>
        </div>
      )}

      {/* Paginated Changes Display */}
      {totalMatching > 0 && viewMode === 'grouped' && (
        <div className="explorer-grouped-container">
          {paginatedGrouped.map(({ group, items }) => {
            const isExpanded = expandedGroups.has(group.id);
            const sigKey = (group.significance || 'medium').toLowerCase();

            const totalInTopic = group.changes?.length ?? group.changeIds?.length ?? items.length;

            return (
              <div key={group.id} className="explorer-topic-accordion">
                <button
                  type="button"
                  className="accordion-header-btn"
                  onClick={() => toggleGroup(group.id)}
                  aria-expanded={isExpanded}
                >
                  <div className="accordion-title-wrap">
                    <span className="accordion-toggle-arrow" aria-hidden="true">
                      {isExpanded ? '▼' : '▶'}
                    </span>
                    <h3 className="accordion-topic-title">{group.topic}</h3>
                    <span className={`ai-sig-badge ai-sig-${sigKey}`}>
                      {sigKey.charAt(0).toUpperCase() + sigKey.slice(1)} Impact
                    </span>
                  </div>
                  <div className="accordion-meta-wrap">
                    <span className="accordion-count-pill">
                      {items.length} on page · {totalInTopic} in topic
                    </span>
                  </div>
                </button>

                {isExpanded && (
                  <div className="accordion-body-content">
                    {group.description && (
                      <p className="accordion-group-desc">{group.description}</p>
                    )}
                    <div className="change-list" aria-live="polite">
                      {items.map((change) => {
                        const globalIndex = changes.findIndex((c) => c.id === change.id);
                        return (
                          <ChangeCard
                            change={change}
                            index={globalIndex !== -1 ? globalIndex : change.id - 1}
                            key={change.id}
                          />
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Flat List View */}
      {totalMatching > 0 && viewMode === 'flat' && (
        <div className="change-list flat-change-list" aria-live="polite">
          {paginatedChanges.map((change) => {
            const globalIndex = changes.findIndex((c) => c.id === change.id);
            return (
              <ChangeCard
                change={change}
                index={globalIndex !== -1 ? globalIndex : change.id - 1}
                key={change.id}
              />
            );
          })}
        </div>
      )}

      {/* Pagination Controls */}
      {totalMatching > 0 && (
        <div className="explorer-pagination-bar" aria-label="Pagination Controls">
          {/* Page size selector */}
          <div className="page-size-selector">
            <span className="page-size-label">Show per page:</span>
            {PAGE_SIZE_OPTIONS.map((size) => (
              <button
                key={size}
                type="button"
                className={`page-size-btn ${pageSize === size ? 'active' : ''}`}
                onClick={() => setPageSize(size)}
              >
                {size}
              </button>
            ))}
          </div>

          {/* Navigation Controls */}
          <div className="pagination-nav-group">
            <button
              type="button"
              className="pagination-btn"
              disabled={safeCurrentPage <= 1}
              onClick={() => setCurrentPage(1)}
              title="First Page"
            >
              « First
            </button>
            <button
              type="button"
              className="pagination-btn"
              disabled={safeCurrentPage <= 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              title="Previous Page"
            >
              ‹ Prev
            </button>

            <span className="pagination-info">
              Page <strong>{safeCurrentPage}</strong> of <strong>{totalPages}</strong>
            </span>

            <button
              type="button"
              className="pagination-btn"
              disabled={safeCurrentPage >= totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              title="Next Page"
            >
              Next ›
            </button>
            <button
              type="button"
              className="pagination-btn"
              disabled={safeCurrentPage >= totalPages}
              onClick={() => setCurrentPage(totalPages)}
              title="Last Page"
            >
              Last »
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
