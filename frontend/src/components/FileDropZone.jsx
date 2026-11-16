import { useId, useRef, useState } from 'react';

const VALID_EXTENSIONS = ['.html', '.htm'];

function isHtmlFile(file) {
  const name = file?.name?.toLowerCase() ?? '';
  return VALID_EXTENSIONS.some((extension) => name.endsWith(extension));
}

export default function FileDropZone({ id, label, subtitle, file, onFileChange }) {
  const inputId = useId();
  const inputRef = useRef(null);
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  function selectFile(candidate) {
    if (!candidate) return;

    if (!isHtmlFile(candidate)) {
      setError('Please select an .html or .htm file.');
      return;
    }

    setError('');
    onFileChange(candidate);
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  function handleRemove(event) {
    event.stopPropagation();
    setError('');
    onFileChange(null);
    if (inputRef.current) inputRef.current.value = '';
  }

  function openPicker() {
    inputRef.current?.click();
  }

  return (
    <section className="upload-column" aria-labelledby={`${id}-heading`}>
      <div className="upload-column-heading">
        <span>{label}</span>
        <h2 id={`${id}-heading`}>{subtitle}</h2>
      </div>

      <div
        className={`drop-zone${isDragging ? ' is-dragging' : ''}${file ? ' has-file' : ''}`}
        onClick={openPicker}
        onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setIsDragging(false);
        }}
        onDrop={handleDrop}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            openPicker();
          }
        }}
        role="button"
        tabIndex="0"
        aria-describedby={`${id}-help ${id}-error`}
      >
        <input
          ref={inputRef}
          id={inputId}
          className="visually-hidden"
          type="file"
          accept=".html,.htm,text/html"
          onChange={(event) => selectFile(event.target.files?.[0])}
          tabIndex="-1"
        />

        {file ? (
          <div className="selected-file">
            <span className="file-icon" aria-hidden="true">HTML</span>
            <div>
              <strong>{file.name}</strong>
              <span>HTML file selected</span>
            </div>
            <div className="file-actions">
              <button type="button" className="text-button" onClick={(event) => { event.stopPropagation(); openPicker(); }}>
                Replace
              </button>
              <button type="button" className="text-button remove-button" onClick={handleRemove}>
                Remove
              </button>
            </div>
          </div>
        ) : (
          <div className="empty-drop-zone">
            <span className="upload-icon" aria-hidden="true">↑</span>
            <strong>Drag &amp; drop HTML file</strong>
            <span id={`${id}-help`}>or choose a file from your computer</span>
            <button type="button" className="browse-button" onClick={(event) => { event.stopPropagation(); openPicker(); }}>
              Browse file
            </button>
          </div>
        )}
      </div>

      <p id={`${id}-error`} className="file-error" role="alert">{error}</p>
    </section>
  );
}
