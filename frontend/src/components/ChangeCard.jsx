import { getChangeSummary, getChangeTitle } from '../utils/summary';
import { generateIndividualExplanation } from '../utils/generateSummary';

function splitStructuredValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }

  if (typeof value !== 'string') return [];
  return value.split(';').map((item) => item.trim()).filter(Boolean);
}

function ValueContent({ value, renderAsList = false }) {
  const items = renderAsList ? splitStructuredValue(value) : [];

  if (items.length > 1) {
    return (
      <ul className="change-value-list">
        {items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{item}</li>)}
      </ul>
    );
  }

  return <strong>{items[0] ?? value}</strong>;
}

function ValueBlock({ label, value, tone, renderAsList = false, compact = false }) {
  if (value === null || value === undefined || value === '') return null;

  return (
    <div className={`value-block value-${tone}${compact ? ' value-compact' : ''}`}>
      {label && <span>{label}</span>}
      <ValueContent value={value} renderAsList={renderAsList} />
    </div>
  );
}

function SectionValue({ value, tone }) {
  if (value === null || value === undefined || value === '') return null;

  const items = splitStructuredValue(value);
  if (items.length <= 1) {
    return <ValueBlock value={value} tone={tone} compact />;
  }

  const previewItems = items.slice(0, 2);

  return (
    <div className={`section-value value-${tone}`}>
      <div className="section-preview">
        {previewItems.map((item, itemIndex) => (
          <p key={`${item}-${itemIndex}`}>{item}</p>
        ))}
      </div>
      <span className="section-item-count">{items.length} contained text items</span>
      {items.length > previewItems.length && (
        <details className="section-content-details">
          <summary>View all section content</summary>
          <ul>
            {items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{item}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}

function isGenericDescription(change, summary) {
  if (!change?.description) return true;

  const description = change.description.trim().toLowerCase();
  const element = getChangeTitle(change).toLowerCase();
  const genericDescriptions = new Set([
    summary.toLowerCase(),
    `${element} was added.`,
    `${element} was removed.`,
    `${element} was updated.`,
    `${element} text was updated.`,
    `${element} attributes were updated.`,
    `${element} text and attributes were updated.`,
  ]);

  return genericDescriptions.has(description);
}

export default function ChangeCard({ change, index }) {
  const title = getChangeTitle(change);
  const summary = getChangeSummary(change);
  const category = ['added', 'removed', 'modified'].includes(change.category)
    ? change.category
    : 'modified';
  const isList = change.type === 'list';
  const isSection = change.type === 'section';
  const explanation = generateIndividualExplanation(change);

  return (
    <article id={`change-${change.id}`} className={`change-card change-${category}`}>
      <div className="change-card-top">
        <span className="change-index">{String(index + 1).padStart(2, '0')}</span>
        <span className={`category-badge badge-${category}`}>{category}</span>
      </div>

      <div className="change-card-body">
        <h3 className="change-title">{title}</h3>
        <p className="change-summary">{summary}</p>

        {category === 'modified' && (change.oldValue != null || change.newValue != null) && (
          <div className="value-comparison">
            <ValueBlock
              label="Before (older version)"
              value={change.oldValue}
              tone="before"
              renderAsList={isList}
            />
            <span className="inline-arrow" aria-hidden="true">→</span>
            <ValueBlock
              label="After (newer version)"
              value={change.newValue}
              tone="after"
              renderAsList={isList}
            />
          </div>
        )}

        {category === 'added' && (
          <div className="single-value-wrap">
            {isSection ? (
              <SectionValue value={change.newValue} tone="after" />
            ) : (
              <ValueBlock
                label="New content (after)"
                value={change.newValue}
                tone="after"
                renderAsList={isList}
                compact
              />
            )}
          </div>
        )}

        {category === 'removed' && (
          <div className="single-value-wrap">
            {isSection ? (
              <SectionValue value={change.oldValue} tone="before" />
            ) : (
              <ValueBlock
                label="Original content (before)"
                value={change.oldValue}
                tone="before"
                renderAsList={isList}
                compact
              />
            )}
          </div>
        )}

        {explanation && (
          <div className="change-explanation-box">
            <span className="explanation-label">Explanation:</span>
            <p className="explanation-text">{explanation}</p>
          </div>
        )}
      </div>
    </article>
  );
}
