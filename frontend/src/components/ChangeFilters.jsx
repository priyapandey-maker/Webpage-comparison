const filters = ['all', 'added', 'removed', 'modified'];

export default function ChangeFilters({ activeFilter, onFilterChange, counts }) {
  return (
    <div className="filter-row" aria-label="Filter changes">
      {filters.map((filter) => {
        const count = filter === 'all' ? counts.total : counts[filter];
        return (
          <button
            className={activeFilter === filter ? 'filter-button active' : 'filter-button'}
            key={filter}
            type="button"
            aria-pressed={activeFilter === filter}
            onClick={() => onFilterChange(filter)}
          >
            <span>{filter}</span>
            <b>{count}</b>
          </button>
        );
      })}
    </div>
  );
}
