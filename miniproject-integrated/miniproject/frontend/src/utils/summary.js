const categoryKeys = ['added', 'removed', 'modified'];

export function calculateChangeCounts(changes = []) {
  return changes.reduce(
    (counts, change) => {
      counts.total += 1;
      if (categoryKeys.includes(change.category)) counts[change.category] += 1;
      return counts;
    },
    { total: 0, added: 0, removed: 0, modified: 0 },
  );
}

function pluralize(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function createDeterministicSummary(changes = []) {
  const counts = calculateChangeCounts(changes);
  return `${pluralize(counts.total, 'change')} ${counts.total === 1 ? 'was' : 'were'} detected between the two webpage versions: ${pluralize(counts.added, 'addition')}, ${pluralize(counts.removed, 'removal')} and ${pluralize(counts.modified, 'modification')}.`;
}

export function getChangeTitle(change) {
  return typeof change?.element === 'string' && change.element.trim()
    ? change.element.trim()
    : 'Content';
}

export function getChangeSummary(change) {
  const element = getChangeTitle(change);
  const normalizedElement = `${element.charAt(0).toLowerCase()}${element.slice(1)}`;

  if (change?.category === 'added') return `New ${normalizedElement} added`;
  if (change?.category === 'removed') return `${element} removed`;
  if (change?.category === 'modified') return `${element} updated`;
  return 'Webpage change';
}
