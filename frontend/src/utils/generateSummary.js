const CATEGORY_CONFIG = {
  added: { noun: 'addition', action: 'added' },
  removed: { noun: 'removal', action: 'removed' },
  modified: { noun: 'modification', action: 'updated' },
};

const TYPE_LABELS = {
  action: 'action',
  button: 'button',
  content: 'content item',
  form: 'form',
  heading: 'heading',
  image: 'image',
  image_source: 'image',
  input: 'input',
  link: 'link',
  link_destination: 'link',
  list: 'list',
  list_item: 'list item',
  media: 'media item',
  page_title: 'page title',
  paragraph: 'paragraph',
  section: 'section',
  table: 'table',
  text: 'text item',
};

const ELEMENT_LABELS = {
  action: 'action',
  button: 'button',
  content: 'content item',
  element: 'element',
  form: 'form',
  heading: 'heading',
  image: 'image',
  'image source': 'image',
  input: 'input',
  link: 'link',
  'link destination': 'link',
  list: 'list',
  'list item': 'list item',
  'media item': 'media item',
  'page title': 'page title',
  paragraph: 'paragraph',
  section: 'section',
  table: 'table',
  text: 'text item',
  'text item': 'text item',
};

const TYPE_PRIORITY = [
  'section',
  'list',
  'heading',
  'paragraph',
  'button',
  'action',
  'link',
  'image',
  'table',
  'form',
  'input',
  'list item',
  'text item',
  'content item',
  'media item',
  'page title',
  'element',
];

const NUMBER_WORDS = [
  'zero',
  'one',
  'two',
  'three',
  'four',
  'five',
  'six',
  'seven',
  'eight',
  'nine',
  'ten',
];

function pluralize(count, singular) {
  if (count === 1) return singular;
  if (singular === 'content item') return 'content items';
  if (singular === 'list item') return 'list items';
  if (singular === 'media item') return 'media items';
  if (singular === 'page title') return 'page titles';
  if (singular === 'text item') return 'text items';
  return `${singular}s`;
}

function formatCount(count, singular) {
  return `${count} ${pluralize(count, singular)}`;
}

function formatNaturalCount(count, singular) {
  const value = NUMBER_WORDS[count] ?? String(count);
  return `${value} ${pluralize(count, singular)}`;
}

function joinNaturally(parts) {
  if (parts.length === 0) return '';
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} and ${parts[1]}`;
  return `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}`;
}

function capitalize(sentence) {
  return sentence ? `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}` : sentence;
}

function getElementLabel(change) {
  const element = typeof change?.element === 'string'
    ? change.element.trim().toLowerCase()
    : '';
  if (ELEMENT_LABELS[element]) return ELEMENT_LABELS[element];

  const type = typeof change?.type === 'string'
    ? change.type.trim().toLowerCase().replaceAll('-', '_').replaceAll(' ', '_')
    : '';
  return TYPE_LABELS[type] ?? 'element';
}

function countElementTypes(changes, category) {
  const counts = new Map();

  changes
    .filter((change) => change?.category === category)
    .forEach((change) => {
      const label = getElementLabel(change);
      counts.set(label, (counts.get(label) ?? 0) + 1);
    });

  return [...counts.entries()].sort(([labelA], [labelB]) => {
    const priorityA = TYPE_PRIORITY.indexOf(labelA);
    const priorityB = TYPE_PRIORITY.indexOf(labelB);
    const normalizedA = priorityA === -1 ? TYPE_PRIORITY.length : priorityA;
    const normalizedB = priorityB === -1 ? TYPE_PRIORITY.length : priorityB;
    return normalizedA - normalizedB || labelA.localeCompare(labelB);
  });
}

function createCountSentence(total, categoryCounts) {
  if (total === 0) {
    return 'No meaningful changes were detected between the two webpage versions.';
  }

  const presentCategories = Object.entries(CATEGORY_CONFIG)
    .filter(([category]) => categoryCounts[category] > 0);
  const recognizedTotal = presentCategories.reduce(
    (sum, [category]) => sum + categoryCounts[category],
    0,
  );
  const otherCount = total - recognizedTotal;

  if (presentCategories.length === 1 && otherCount === 0) {
    const [category, config] = presentCategories[0];
    const count = categoryCounts[category];
    if (total === 1) {
      return `1 meaningful change was detected, which was ${config.noun === 'addition' ? 'an' : 'a'} ${config.noun}.`;
    }
    return `${total} meaningful changes were detected, all of which are ${pluralize(count, config.noun)}.`;
  }

  const categoryParts = presentCategories.map(([category, config]) => (
    formatCount(categoryCounts[category], config.noun)
  ));
  if (otherCount > 0) categoryParts.push(formatCount(otherCount, 'other change'));

  return `${total} meaningful ${total === 1 ? 'change was' : 'changes were'} detected: ${joinNaturally(categoryParts)}.`;
}

function createTypeSentence(changes, category) {
  const entries = countElementTypes(changes, category);
  if (entries.length === 0) return null;

  const subject = capitalize(joinNaturally(
    entries.map(([label, count]) => formatNaturalCount(count, label)),
  ));
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  const action = CATEGORY_CONFIG[category].action;
  return `${subject} ${total === 1 ? 'was' : 'were'} ${action}.`;
}

export function generateChangeSummary(changes = []) {
  const safeChanges = Array.isArray(changes) ? changes.filter(Boolean) : [];
  if (safeChanges.length === 0) {
    return ['No meaningful changes were detected between the two webpage versions.'];
  }

  const categoryCounts = safeChanges.reduce(
    (counts, change) => {
      if (CATEGORY_CONFIG[change?.category]) counts[change.category] += 1;
      return counts;
    },
    { added: 0, removed: 0, modified: 0 },
  );

  return [
    createCountSentence(safeChanges.length, categoryCounts),
    createTypeSentence(safeChanges, 'added'),
    createTypeSentence(safeChanges, 'modified'),
    createTypeSentence(safeChanges, 'removed'),
  ].filter(Boolean);
}
