export default function ComparisonHeader({ version1, version2 }) {
  return (
    <header className="comparison-header">
      <div className="eyebrow">Comparison report</div>
      <h1>Historical Webpage Comparison</h1>
      <p className="header-intro">A structured view of verified content and functionality changes.</p>

      <div className="version-flow" aria-label={`${version1.label} compared with ${version2.label}`}>
        <div className="version-block">
          <span>Previous version</span>
          <strong>{version1.label}</strong>
        </div>
        <span className="version-arrow" aria-hidden="true">↓</span>
        <div className="version-block version-block-current">
          <span>Current version</span>
          <strong>{version2.label}</strong>
        </div>
      </div>
    </header>
  );
}
