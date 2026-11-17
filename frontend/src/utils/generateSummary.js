const TECHNICAL_EXTENSIONS = [
  '.css', '.js', '.ico', '.png', '.jpg', '.jpeg', '.svg', '.gif',
  '.woff', '.woff2', '.ttf', '.eot', '.map', '.json', '.xml',
];

const TECHNICAL_TERMS = new Set([
  'href', 'rel', 'stylesheet', 'shortcut', 'icon', 'static', 'css', 'img',
  'html', 'body', 'div', 'span', 'p', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'li', 'ol', 'table', 'tbody', 'thead', 'tr', 'td', 'th', 'type', 'image',
  'http', 'https', 'url', 'uri', 'ftp', 'www',
  'paragraph', 'footer', 'header', 'element',
]);

const HREF_PATTERN = /^(.*?)\s*\(href:\s*(.*?)\)$/i;

export function isTechnicalNoise(term) {
  if (!term || typeof term !== 'string') return true;
  const s = term.trim().toLowerCase();
  if (s.length < 2) return true;

  // DOM paths or XPath locators
  if (s.startsWith('/html') || s.includes('body[') || s.includes('div[') || s.includes('p[')) {
    return true;
  }

  // URLs, URIs, endpoints, path fragments
  if (
    s.startsWith('/') ||
    s.startsWith('http://') ||
    s.startsWith('https://') ||
    s.startsWith('#') ||
    s.startsWith('//') ||
    s.endsWith('/') ||
    s.endsWith('\\') ||
    s.includes('/') ||
    s.includes('\\')
  ) {
    return true;
  }
  if (s.includes('http://') || s.includes('https://')) {
    return true;
  }

  // File extensions
  for (const ext of TECHNICAL_EXTENSIONS) {
    if (s.endsWith(ext) || s.includes(ext + ' ')) return true;
  }

  // Attribute syntax
  if (s.includes('href:') || s.includes('rel:') || s.includes('type:')) {
    return true;
  }

  // Hexadecimal hashes / cache-busting tokens (e.g. 68dd615b61e5)
  if (/^[0-9a-f]{7,}$/.test(s) && /\d/.test(s)) {
    return true;
  }

  // Standalone technical tokens
  const tokens = s.match(/[a-z0-9_-]+/g) || [];
  if (tokens.length > 0 && tokens.every((tok) => TECHNICAL_TERMS.has(tok) || !isNaN(tok))) {
    return true;
  }

  return false;
}

function cleanText(text) {
  if (!text) return '';
  return String(text).trim().replace(/\s+/g, ' ');
}

function truncate(text, maxLen = 65) {
  const clean = cleanText(text);
  if (!clean) return '';
  return clean.length > maxLen ? `${clean.slice(0, maxLen)}...` : clean;
}

function extractItemLabel(raw) {
  if (!raw) return '';
  const s = String(raw).trim();
  if (s.startsWith('/html') || s.includes('body[')) {
    const container = s.includes('footer')
      ? 'in the footer'
      : s.includes('header')
      ? 'in the header'
      : s.includes('nav')
      ? 'in the navigation area'
      : 'in the page layout';
    return `an element ${container}`;
  }
  const firstPart = s.split(';')[0].trim();
  const stripped = firstPart.replace(/^[\p{Emoji}\p{Symbol}\s]+/u, '').trim();
  return stripped || firstPart;
}

function isDateLike(str) {
  if (!str) return false;
  const s = String(str);
  return /\b(19\d\d|20\d\d)\b/.test(s) ||
    /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b/i.test(s);
}

function joinPhrases(items) {
  if (!items || items.length === 0) return '';
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`;
}

export function generateIndividualExplanation(change) {
  if (!change) return 'No change details available.';

  const category = change.category || 'modified';
  const element = change.element || 'Content';
  const type = change.type || '';
  const oldVal = cleanText(change.oldValue);
  const newVal = cleanText(change.newValue);

  // 1. Link label and destination parsing
  const mOld = HREF_PATTERN.exec(oldVal);
  const mNew = HREF_PATTERN.exec(newVal);

  if (category === 'modified') {
    if (mOld && mNew) {
      const oldLabel = mOld[1].trim();
      const oldHref = mOld[2].trim();
      const newLabel = mNew[1].trim();
      const newHref = mNew[2].trim();

      if (oldLabel !== newLabel && oldHref !== newHref) {
        return `Link label changed from '${truncate(oldLabel)}' to '${truncate(newLabel)}', and its destination changed from '${oldHref}' to '${newHref}'.`;
      }
      if (oldLabel !== newLabel) {
        return `Link label changed from '${truncate(oldLabel)}' to '${truncate(newLabel)}' (destination remains '${oldHref}').`;
      }
      if (oldHref !== newHref) {
        return `Link destination changed from '${oldHref}' to '${newHref}' (label remains '${truncate(oldLabel)}').`;
      }
    }

    if (type === 'link_destination' || ((oldVal.startsWith('/') || oldVal.startsWith('http')) && (newVal.startsWith('/') || newVal.startsWith('http')))) {
      if (oldVal.startsWith('http://') && newVal.startsWith('https://')) {
        return `Link destination updated from '${oldVal}' to '${newVal}' (upgraded to secure HTTPS).`;
      }
      return `Link destination updated from '${oldVal}' to '${newVal}'.`;
    }

    // If backend NLP provided a non-generic explanation and it wasn't a link
    if (typeof change.explanation === 'string' && change.explanation.trim()) {
      return change.explanation.trim();
    }

    const elLower = element.toLowerCase();
    const oldLower = oldVal.toLowerCase();
    const newLower = newVal.toLowerCase();
    if (
      elLower.includes('link element') ||
      oldLower.includes('rel: stylesheet') ||
      newLower.includes('rel: stylesheet') ||
      oldLower.includes('rel: shortcut') ||
      newLower.includes('rel: shortcut')
    ) {
      if (oldLower.includes('stylesheet') || newLower.includes('stylesheet')) {
        return 'Technical asset reference updated (stylesheet).';
      }
      if (oldLower.includes('icon') || newLower.includes('icon') || oldLower.includes('shortcut') || newLower.includes('shortcut')) {
        return 'Technical asset reference updated (shortcut icon).';
      }
      return 'Technical asset or resource reference was updated.';
    }

    if (type === 'page_title' || element.toLowerCase() === 'page title') {
      return `Page title updated from '${truncate(oldVal)}' to '${truncate(newVal)}'.`;
    }
    if (type === 'heading' || element.toLowerCase().includes('heading')) {
      return `Heading updated from '${truncate(oldVal)}' to '${truncate(newVal)}'.`;
    }
    if (type === 'image_source') {
      return `Image source updated from '${truncate(oldVal)}' to '${truncate(newVal)}'.`;
    }
    if (isDateLike(oldVal) && isDateLike(newVal)) {
      return `Date or deadline updated from '${truncate(oldVal)}' to '${truncate(newVal)}'.`;
    }
    if (oldVal && newVal) {
      return `Text updated from '${truncate(oldVal)}' to '${truncate(newVal)}'.`;
    }
    if (newVal) {
      return `Text updated to '${truncate(newVal)}'.`;
    }
    return `${element} was updated.`;
  }

  // 2. Additions
  if (category === 'added') {
    if (type === 'section' || element.toLowerCase() === 'section') {
      const title = extractItemLabel(newVal);
      return title
        ? `New section '${title}' was introduced. This content was absent from the older version.`
        : 'New section was introduced. This content was absent from the older version.';
    }
    if (type === 'link' || element.toLowerCase() === 'link') {
      return `New link '${truncate(newVal)}' was added. This link was absent from the older version.`;
    }
    if (type === 'list' || type === 'list_item') {
      return `New list item '${truncate(newVal)}' was added. This was absent from the older version.`;
    }
    if (newVal) {
      return `New content was introduced: '${truncate(newVal)}'. This content was absent from the older version.`;
    }
    return `New ${element.toLowerCase()} was introduced. This content was absent from the older version.`;
  }

  // 3. Removals
  if (category === 'removed') {
    if (oldVal.startsWith('/html') || oldVal.includes('body[')) {
      const container = oldVal.includes('footer')
        ? 'in the footer'
        : oldVal.includes('header')
        ? 'in the header'
        : oldVal.includes('nav')
        ? 'in the navigation area'
        : 'on the page';
      return `An empty ${element.toLowerCase()} ${container} was removed and is no longer present in the newer version.`;
    }
    if (oldVal.toLowerCase().startsWith('empty ') && oldVal.toLowerCase().includes(' in the ')) {
      return `An ${oldVal.toLowerCase()} was removed and is no longer present in the newer version.`;
    }
    if (type === 'button' || element.toLowerCase() === 'button') {
      return `The '${truncate(oldVal)}' action button was removed from the webpage and is no longer present in the newer version.`;
    }
    if (type === 'link' || element.toLowerCase() === 'link') {
      return `The link '${truncate(oldVal)}' was removed and is no longer present in the newer version.`;
    }
    if (type === 'section' || element.toLowerCase() === 'section') {
      const title = extractItemLabel(oldVal);
      return title
        ? `The '${title}' section was removed and is no longer present in the newer version.`
        : 'This section was removed and is no longer present in the newer version.';
    }
    if (oldVal) {
      return `Content '${truncate(oldVal)}' was removed and is no longer present in the newer version.`;
    }
    return `The ${element.toLowerCase()} was removed and is no longer present in the newer version.`;
  }

  return `${element} was modified.`;
}

export function generateChangeSummary(changes = [], nlpAnalysis = null) {
  const safeChanges = Array.isArray(changes) ? changes.filter(Boolean) : [];

  if (safeChanges.length === 0) {
    const zeroMsg = 'No meaningful changes were detected between the two webpage versions.';
    const result = [zeroMsg];
    result.overview = zeroMsg;
    result.modifications = [];
    result.additions = [];
    result.removals = [];
    result.nlpSummary = null;
    return result;
  }

  const modifications = safeChanges.filter((c) => c.category === 'modified');
  const additions = safeChanges.filter((c) => c.category === 'added');
  const removals = safeChanges.filter((c) => c.category === 'removed');

  // --- 1. Identify Title / Main Heading updates ---
  const titleMods = modifications.filter(
    (c) => c.type === 'page_title' || c.element?.toLowerCase().includes('heading') || c.type === 'heading'
  );
  const dateMods = modifications.filter(
    (c) => !titleMods.includes(c) && isDateLike(c.oldValue) && isDateLike(c.newValue)
  );
  const linkMods = modifications.filter(
    (c) => c.type === 'link' || c.type === 'link_destination' || c.element?.toLowerCase().includes('link')
  );
  const contentMods = modifications.filter(
    (c) => !titleMods.includes(c) && !dateMods.includes(c) && !linkMods.includes(c)
  );

  // --- 2. Build High-Level Narrative Sentence (Overview) ---
  const narrativeParts = [];

  if (titleMods.length > 0) {
    const pageTitleMod = titleMods.find((c) => c.type === 'page_title' || c.element?.toLowerCase() === 'page title');
    const h1Mod = titleMods.find((c) => c.sourcePath?.includes('/h1[') || c.targetPath?.includes('/h1['));
    const primaryTitle = pageTitleMod || h1Mod || titleMods[0];
    const oldTitle = truncate(primaryTitle.oldValue, 45);
    const newTitle = truncate(primaryTitle.newValue, 45);
    narrativeParts.push(
      `The newer webpage contains updated title and heading content (transitioning from '${oldTitle}' to '${newTitle}')`
    );
  } else if (linkMods.length >= 2) {
    // Navigation / menu link changes
    const sampleLinkMods = linkMods.filter((c) => {
      const m1 = HREF_PATTERN.exec(c.oldValue || '');
      const m2 = HREF_PATTERN.exec(c.newValue || '');
      return m1 && m2 && m1[1].trim() !== m2[1].trim();
    });
    if (sampleLinkMods.length > 0) {
      const preview = sampleLinkMods.slice(0, 2).map((c) => {
        const m1 = HREF_PATTERN.exec(c.oldValue);
        const m2 = HREF_PATTERN.exec(c.newValue);
        return `'${truncate(m1[1].trim(), 20)}' → '${truncate(m2[1].trim(), 20)}'`;
      });
      narrativeParts.push(
        `The newer webpage features updated navigation and menu links (including revisions such as ${joinPhrases(preview)})`
      );
    } else {
      narrativeParts.push('The newer webpage features updated navigation links and revised page content');
    }
  } else {
    narrativeParts.push('The newer webpage contains revised content and structural updates');
  }

  const actionParts = [];
  if (modifications.length > 0) {
    actionParts.push(`${modifications.length} content modification${modifications.length === 1 ? '' : 's'}`);
  }
  if (additions.length > 0) {
    actionParts.push(`${additions.length} new addition${additions.length === 1 ? '' : 's'}`);
  }
  if (removals.length > 0) {
    actionParts.push(`${removals.length} removal${removals.length === 1 ? '' : 's'}`);
  }

  const overviewSentence = `${narrativeParts[0]}, with a total of ${safeChanges.length} detected changes (${joinPhrases(actionParts)}).`;

  // --- 3. Build Detailed Modifications Sentence ---
  let modificationSentence = null;
  if (modifications.length > 0) {
    const modHighlights = [];

    // Title / heading modification highlight
    if (titleMods.length > 0) {
      const pageTitleMod = titleMods.find((c) => c.type === 'page_title' || c.element?.toLowerCase() === 'page title');
      const h1Mod = titleMods.find((c) => c.sourcePath?.includes('/h1[') || c.targetPath?.includes('/h1['));
      const primaryTitle = pageTitleMod || h1Mod || titleMods[0];
      const otherTitle = titleMods.find((c) => c !== primaryTitle && c.oldValue && c.newValue && c.oldValue !== c.newValue);
      const highlightTitle = otherTitle || primaryTitle;
      if (highlightTitle && highlightTitle.oldValue && highlightTitle.newValue) {
        modHighlights.push(`headings updated such as '${truncate(highlightTitle.oldValue, 35)}' → '${truncate(highlightTitle.newValue, 35)}'`);
      }
    }

    // Date modification highlight
    if (dateMods.length > 0) {
      const topDate = dateMods[0];
      modHighlights.push(`key dates updated from '${truncate(topDate.oldValue, 25)}' to '${truncate(topDate.newValue, 25)}'`);
    }

    // Link modification highlight
    if (linkMods.length > 0) {
      const sampleLink = linkMods.find((c) => {
        const m1 = HREF_PATTERN.exec(c.oldValue || '');
        const m2 = HREF_PATTERN.exec(c.newValue || '');
        return m1 && m2 && (m1[1].trim() !== m2[1].trim() || m1[2].trim() !== m2[2].trim());
      });
      if (sampleLink) {
        const m1 = HREF_PATTERN.exec(sampleLink.oldValue);
        const m2 = HREF_PATTERN.exec(sampleLink.newValue);
        modHighlights.push(`navigation links updated such as '${truncate(m1[1].trim(), 20)}' (${m1[2].trim()}) → '${truncate(m2[1].trim(), 20)}' (${m2[2].trim()})`);
      }

      const httpsUpgrades = linkMods.filter(
        (c) => c.oldValue?.startsWith('http://') && c.newValue?.startsWith('https://')
      );
      if (httpsUpgrades.length > 0) {
        modHighlights.push(`link destinations upgraded to secure HTTPS`);
      }
    }

    // Content modification highlight
    if (contentMods.length > 0) {
      const topContent = contentMods.find((c) => c.oldValue && c.newValue && !isTechnicalNoise(c.oldValue));
      if (topContent) {
        modHighlights.push(`revisions to ${topContent.element.toLowerCase()} text`);
      }
    }

    // Technical asset modifications (stylesheets, icons)
    const techAssetMods = modifications.filter((c) => {
      const el = (c.element || '').toLowerCase();
      const oldV = (c.oldValue || '').toLowerCase();
      const newV = (c.newValue || '').toLowerCase();
      return (
        el.includes('link element') ||
        oldV.includes('rel: stylesheet') ||
        newV.includes('rel: stylesheet') ||
        oldV.includes('rel: shortcut') ||
        newV.includes('rel: shortcut') ||
        oldV.includes('.css') ||
        newV.includes('.css') ||
        oldV.includes('.ico') ||
        newV.includes('.ico')
      );
    });
    if (techAssetMods.length > 0) {
      modHighlights.push('technical asset updates (stylesheet and icon references)');
    }

    if (modHighlights.length > 0) {
      modificationSentence = `Modified content includes ${joinPhrases(modHighlights)}.`;
    } else {
      modificationSentence = `${modifications.length} existing content section${modifications.length === 1 ? ' was' : 's were'} revised.`;
    }
  }

  // --- 4. Build Detailed Additions Sentence ---
  let additionSentence = null;
  if (additions.length > 0) {
    const addedSectionTitles = additions
      .filter((c) => c.type === 'section' || c.element?.toLowerCase() === 'section')
      .map((c) => extractItemLabel(c.newValue))
      .filter((t) => t && !isTechnicalNoise(t));

    const addedLinks = additions
      .filter((c) => c.type === 'link' || c.element?.toLowerCase() === 'link' || c.type === 'list_item')
      .map((c) => truncate(c.newValue, 30))
      .filter((t) => t && !isTechnicalNoise(t));

    const addedHighlights = [];
    if (addedSectionTitles.length > 0) {
      const preview = addedSectionTitles.slice(0, 3).map((t) => `'${t}'`);
      addedHighlights.push(`new sections covering ${joinPhrases(preview)}`);
    }
    if (addedLinks.length > 0) {
      const preview = addedLinks.slice(0, 3).map((l) => `'${l}'`);
      addedHighlights.push(`new links for ${joinPhrases(preview)}`);
    }

    if (addedHighlights.length > 0) {
      additionSentence = `Newly introduced items include ${joinPhrases(addedHighlights)}, which were not present in the earlier version.`;
    } else {
      const sampleAdd = additions.find((c) => c.newValue && !isTechnicalNoise(c.newValue));
      if (sampleAdd) {
        additionSentence = `Newly introduced content includes '${truncate(sampleAdd.newValue, 50)}', absent from the previous version.`;
      } else {
        additionSentence = `${additions.length} new content element${additions.length === 1 ? ' was' : 's were'} added to the webpage.`;
      }
    }
  }

  // --- 5. Build Detailed Removals Sentence ---
  let removalSentence = null;
  if (removals.length > 0) {
    const removedNames = removals.map((r) => {
      const rawVal = cleanText(r.oldValue);
      if (rawVal.startsWith('/html') || rawVal.includes('body[')) {
        const container = rawVal.includes('footer')
          ? 'in the footer'
          : rawVal.includes('header')
          ? 'in the header'
          : 'on the page';
        return `an empty ${r.element ? r.element.toLowerCase() : 'element'} ${container}`;
      }
      if (rawVal.toLowerCase().startsWith('empty ') && rawVal.toLowerCase().includes(' in the ')) {
        return `an ${rawVal.toLowerCase()}`;
      }
      const label = extractItemLabel(rawVal);
      const elem = r.element ? r.element.toLowerCase() : 'item';
      return label ? `'${truncate(label, 30)}' (${elem})` : `one ${elem}`;
    });

    if (removedNames.length > 0) {
      const preview = removedNames.slice(0, 3);
      removalSentence = `Content removed from the previous version includes ${joinPhrases(preview)}, which is no longer present.`;
    } else {
      removalSentence = `${removals.length} item${removals.length === 1 ? '' : 's'} present in the older version ${removals.length === 1 ? 'is' : 'are'} no longer present.`;
    }
  }

  // --- 6. NLP Semantic Insight Sentence (if available) ---
  let nlpSentence = null;
  if (nlpAnalysis?.overall && typeof nlpAnalysis.overall === 'object') {
    const overall = nlpAnalysis.overall;
    const parts = [];
    if (typeof overall.average_semantic_similarity === 'number') {
      const pct = (overall.average_semantic_similarity * 100).toFixed(1);
      parts.push(`average semantic similarity of ${pct}% across modified text`);
    }
    if (Array.isArray(overall.top_added_keywords)) {
      const cleanKws = overall.top_added_keywords.filter((k) => !isTechnicalNoise(k));
      if (cleanKws.length > 0) {
        const preview = cleanKws.slice(0, 4).map((k) => `'${k}'`);
        parts.push(`prominent new terminology such as ${joinPhrases(preview)}`);
      }
    }
    if (parts.length > 0) {
      nlpSentence = `Semantic analysis reveals an ${joinPhrases(parts)}.`;
    }
  }

  const sentences = [
    overviewSentence,
    modificationSentence,
    additionSentence,
    removalSentence,
    nlpSentence,
  ].filter(Boolean);

  // Attach structured properties for modern UI components while preserving array interface
  sentences.overview = overviewSentence;
  sentences.modifications = modificationSentence;
  sentences.additions = additionSentence;
  sentences.removals = removalSentence;
  sentences.nlpSummary = nlpSentence;

  return sentences;
}
