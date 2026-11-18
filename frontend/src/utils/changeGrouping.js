/**
 * Utility for grouping detected changes into structured, navigable topic groups.
 * Reuses AI-generated topic groups when available, and provides deterministic fallback
 * grouping when AI summary is unavailable or null.
 */

export function isTechnicalAsset(change) {
  if (!change) return false;
  const elem = String(change.element || change.type || '').toLowerCase();
  const exp = String(change.explanation || '').toLowerCase();
  const oldVal = String(change.oldValue || '').toLowerCase();
  const newVal = String(change.newValue || '').toLowerCase();

  if (
    exp.includes('technical asset') ||
    exp.includes('stylesheet') ||
    exp.includes('shortcut icon') ||
    exp.includes('favicon')
  ) {
    return true;
  }
  if (elem.includes('link element') || elem.includes('script') || elem.includes('style element')) {
    return true;
  }
  if (
    oldVal.includes('rel: stylesheet') ||
    newVal.includes('rel: stylesheet') ||
    oldVal.includes('rel: shortcut') ||
    newVal.includes('rel: shortcut')
  ) {
    return true;
  }
  return false;
}

export function isNavigationChange(change) {
  if (!change || isTechnicalAsset(change)) return false;
  const elem = String(change.element || change.type || '').toLowerCase();
  const t = String(change.type || '').toLowerCase();
  const exp = String(change.explanation || '').toLowerCase();
  const path1 = String(change.sourcePath || '').toLowerCase();
  const path2 = String(change.targetPath || '').toLowerCase();
  const paths = `${path1} ${path2}`;

  return (
    elem.includes('link') ||
    elem.includes('nav') ||
    elem.includes('button') ||
    elem.includes('menu') ||
    t === 'link' ||
    t === 'button' ||
    t === 'nav' ||
    exp.includes('link') ||
    exp.includes('navigation') ||
    exp.includes('destination') ||
    exp.includes('button') ||
    exp.includes('menu') ||
    paths.includes('/nav') ||
    paths.includes('/menu')
  );
}

const SCHEMA_METADATA_TOKENS = new Set([
  'topic_groups',
  'change_ids',
  'executive_summary',
  'significance',
  'key_takeaways',
  'topic',
  'category',
  'description',
  'changes',
  'summary',
]);

/**
 * Sanitizes key takeaways to remove internal schema artifacts,
 * and neutralize unsupported promotional or subjective claims
 * into factual, grounded phrasing.
 */
export function sanitizeKeyTakeaway(takeaway) {
  if (typeof takeaway !== 'string') return '';
  let clean = takeaway.trim();
  if (!clean) return '';

  // Strip leading list bullets or numbering
  clean = clean.replace(/^([-*•]|\d+\.)\s*/, '').trim();

  // Filter out JSON syntax fragments and raw brackets
  if (clean.startsWith('{') || clean.startsWith('[') || clean.endsWith('}') || clean.endsWith(']')) {
    return '';
  }

  // Filter out internal schema tokens and raw metadata names
  const cleanLower = clean.toLowerCase().replace(/[`'"\s:;{}[\]]/g, '');
  if (SCHEMA_METADATA_TOKENS.has(cleanLower) || cleanLower.startsWith('topic_groups')) {
    return '';
  }
  if (cleanLower.length < 5) {
    return '';
  }

  return clean
    .replace(/\bbeing moved to a sidebar and hidden\b/gi, 'menu and sidebar navigation updated')
    .replace(/\bmoved to a sidebar and hidden\b/gi, 'menu and sidebar navigation updated')
    .replace(/\bmoved to a sidebar\b/gi, 'updated in sidebar navigation')
    .replace(/\bhas been simplified with\b/gi, 'has been updated with')
    .replace(/\bhas been simplified to\b/gi, 'has been updated to')
    .replace(/\bwas simplified to\b/gi, 'was updated to')
    .replace(/\bwas simplified with\b/gi, 'was updated with')
    .replace(/\bis now simplified\b/gi, 'has been updated')
    .replace(/\bhas been streamlined\b/gi, 'has been updated')
    .replace(/\bhas been improved\b/gi, 'has been updated')
    .replace(/\bhas been enhanced\b/gi, 'has been updated')
    .replace(/\bhas been optimized\b/gi, 'has been updated')
    .replace(/\bis much improved\b/gi, 'has been updated')
    .replace(/\bprovides a better\b/gi, 'provides an updated')
    .replace(/\bprovides a more seamless\b/gi, 'provides an updated');
}

/**
 * Validates and sanitizes a topic group's title and description based on the actual
 * constituent changes. Avoids misleading labels (e.g. 'Brand and Design' for navigation links).
 */
export function sanitizeTopicGroup(group) {
  if (!group || !Array.isArray(group.changes) || group.changes.length === 0) {
    return group;
  }

  const topicLower = String(group.topic || '').trim().toLowerCase();
  const total = group.changes.length;
  const assetCount = group.changes.filter(isTechnicalAsset).length;
  const navCount = group.changes.filter((c) => !isTechnicalAsset(c) && isNavigationChange(c)).length;
  const contentCount = total - assetCount - navCount;

  const addedCount = group.changes.filter((c) => c.category === 'added').length;

  const isBrandOrDesign =
    topicLower.includes('brand') ||
    topicLower.includes('design') ||
    topicLower.includes('styling') ||
    topicLower.includes('theme');

  const hasActualDesignElements = group.changes.some((c) => {
    const elem = String(c.element || c.type || '').toLowerCase();
    const exp = String(c.explanation || '').toLowerCase();
    const desc = String(c.description || '').toLowerCase();
    return (
      elem.includes('style') ||
      elem.includes('css') ||
      elem.includes('logo') ||
      elem.includes('image') ||
      elem.includes('img') ||
      exp.includes('logo') ||
      exp.includes('theme') ||
      desc.includes('logo') ||
      desc.includes('theme')
    );
  });

  // Rule 1: Correct misleading "Brand and Design" if no visual or styling assets exist
  if (isBrandOrDesign && !hasActualDesignElements && assetCount === 0) {
    if (navCount > 0 && contentCount === 0) {
      group.topic = 'Navigation & Action Links';
      group.description = 'Updates to navigation links, application buttons, and destination paths.';
      group.significance = 'medium';
    } else if (contentCount > 0 && navCount === 0) {
      if (addedCount === total) {
        group.topic = 'New Content Additions';
        group.description = 'New structural sections and content items added to the page.';
        group.significance = 'medium';
      } else {
        group.topic = 'Page Information & Content';
        group.description = 'Updates to page text, headings, dates, and contact details.';
        group.significance = 'medium';
      }
    } else if (navCount > 0 && contentCount > 0) {
      group.topic = 'Page Updates & Links';
      group.description = 'Updates to page content items, navigation links, and action buttons.';
      group.significance = 'medium';
    }
  }

  // Rule 2: Correct misleading "Technical Assets" if no technical assets are in the group
  if ((topicLower.includes('asset') || topicLower.includes('technical')) && assetCount === 0) {
    if (navCount > 0 && contentCount === 0) {
      group.topic = 'Navigation Changes';
      group.description = 'Updates to links, menus, and destination paths.';
      group.significance = 'medium';
    } else {
      group.topic = 'Content Updates';
      group.description = 'Additions, removals, and revisions to page content.';
      group.significance = 'medium';
    }
  }

  // Rule 3: Correct misleading "Navigation" if no navigation items are in the group
  if ((topicLower.includes('nav') || topicLower.includes('menu') || topicLower.includes('link')) && navCount === 0) {
    if (assetCount > 0 && contentCount === 0) {
      group.topic = 'Technical Asset Updates';
      group.description = 'Updates to stylesheets, favicon, and technical resources.';
      group.significance = 'low';
    } else {
      group.topic = 'Content Updates';
      group.description = 'Additions, removals, and revisions to page content.';
      group.significance = 'medium';
    }
  }

  return group;
}

/**
 * Builds structured topic groups from comparison changes and optional AI summary.
 * Guarantees that 100% of detected changes are represented in exactly one group.
 * Unknown IDs are ignored, duplicate claims across AI groups are removed,
 * unassigned changes are routed into deterministic fallback groups, and
 * misleading labels are sanitized.
 *
 * @param {Array} changes - The full list of change objects from the comparison engine.
 * @param {Object|null} aiSummary - The optional AI summary object from backend.
 * @returns {Array} Array of topic group objects: { id, topic, description, significance, changes, changeIds }
 */
export function buildTopicGroups(changes = [], aiSummary = null) {
  if (!Array.isArray(changes) || changes.length === 0) {
    return [];
  }

  const changeMap = new Map();
  for (const c of changes) {
    if (c && c.id != null) {
      changeMap.set(Number(c.id), c);
    }
  }

  const aiGroups = Array.isArray(aiSummary?.topic_groups) ? aiSummary.topic_groups : [];

  // Case 1: AI Topic Groups Available
  if (aiGroups.length > 0) {
    const assignedIds = new Set();
    const resultGroups = [];

    for (let idx = 0; idx < aiGroups.length; idx++) {
      const g = aiGroups[idx];
      const rawIds = Array.isArray(g.change_ids)
        ? g.change_ids
        : Array.isArray(g.changeIds)
        ? g.changeIds
        : [];
      const groupChanges = [];

      for (const id of rawIds) {
        const numId = Number(id);
        if (changeMap.has(numId) && !assignedIds.has(numId)) {
          groupChanges.push(changeMap.get(numId));
          assignedIds.add(numId);
        }
      }

      if (groupChanges.length > 0) {
        const createdGroup = {
          id: `ai-group-${idx}`,
          topic: g.topic || `Topic Group ${idx + 1}`,
          description: g.description || 'Related detected changes.',
          significance: (g.significance || 'medium').toLowerCase(),
          changes: groupChanges,
          changeIds: groupChanges.map((c) => c.id),
        };
        resultGroups.push(sanitizeTopicGroup(createdGroup));
      }
    }

    // Safety fallback: every change not claimed by an AI group is assigned to a deterministic fallback group
    const unassignedChanges = changes.filter((c) => !assignedIds.has(Number(c.id)));
    if (unassignedChanges.length > 0) {
      const unassignedAssets = unassignedChanges.filter(isTechnicalAsset);
      const unassignedNav = unassignedChanges.filter((c) => !isTechnicalAsset(c) && isNavigationChange(c));
      const unassignedContent = unassignedChanges.filter((c) => !isTechnicalAsset(c) && !isNavigationChange(c));

      if (unassignedAssets.length > 0) {
        resultGroups.push({
          id: 'fallback-assets',
          topic: 'Technical Asset Updates',
          description: 'Updates to stylesheet, favicon, and technical resource references.',
          significance: 'low',
          changes: unassignedAssets,
          changeIds: unassignedAssets.map((c) => c.id),
        });
        unassignedAssets.forEach((c) => assignedIds.add(Number(c.id)));
      }

      if (unassignedNav.length > 0) {
        resultGroups.push({
          id: 'fallback-nav',
          topic: 'Navigation Changes',
          description: 'Updates to page navigation links, destinations, and paths.',
          significance: 'medium',
          changes: unassignedNav,
          changeIds: unassignedNav.map((c) => c.id),
        });
        unassignedNav.forEach((c) => assignedIds.add(Number(c.id)));
      }

      if (unassignedContent.length > 0) {
        const unassignedAdded = unassignedContent.filter((c) => c.category === 'added');
        const unassignedRemoved = unassignedContent.filter((c) => c.category === 'removed');
        const unassignedModified = unassignedContent.filter((c) => c.category === 'modified');

        if (unassignedAdded.length > 0) {
          resultGroups.push({
            id: 'fallback-added',
            topic: 'New Content & Sections',
            description: 'New structural sections, lists, and content added to the page.',
            significance: 'medium',
            changes: unassignedAdded,
            changeIds: unassignedAdded.map((c) => c.id),
          });
          unassignedAdded.forEach((c) => assignedIds.add(Number(c.id)));
        }

        if (unassignedRemoved.length > 0) {
          resultGroups.push({
            id: 'fallback-removed',
            topic: 'Removed Webpage Content',
            description: 'Sections and content pruned from the newer version.',
            significance: 'medium',
            changes: unassignedRemoved,
            changeIds: unassignedRemoved.map((c) => c.id),
          });
          unassignedRemoved.forEach((c) => assignedIds.add(Number(c.id)));
        }

        if (unassignedModified.length > 0) {
          resultGroups.push({
            id: 'fallback-modified',
            topic: 'Content Updates',
            description: 'Revisions to page text, headings, and descriptions.',
            significance: 'medium',
            changes: unassignedModified,
            changeIds: unassignedModified.map((c) => c.id),
          });
          unassignedModified.forEach((c) => assignedIds.add(Number(c.id)));
        }
      }
    }

    return resultGroups.filter((g) => Array.isArray(g.changes) && g.changes.length > 0);
  }

  // Case 2: Deterministic Fallback Grouping (when AI summary is null / disabled)
  const navChanges = [];
  const assetChanges = [];
  const addedChanges = [];
  const removedChanges = [];
  const modifiedChanges = [];

  for (const c of changes) {
    if (isTechnicalAsset(c)) {
      assetChanges.push(c);
    } else if (isNavigationChange(c)) {
      navChanges.push(c);
    } else if (c.category === 'added') {
      addedChanges.push(c);
    } else if (c.category === 'removed') {
      removedChanges.push(c);
    } else {
      modifiedChanges.push(c);
    }
  }

  const fallbackGroups = [];

  if (navChanges.length > 0) {
    fallbackGroups.push({
      id: 'det-nav',
      topic: 'Navigation & Menu Changes',
      description: 'Additions, removals, and destination updates for links and menus.',
      significance: 'high',
      changes: navChanges,
      changeIds: navChanges.map((c) => c.id),
    });
  }

  if (addedChanges.length > 0) {
    fallbackGroups.push({
      id: 'det-added',
      topic: 'New Content Additions',
      description: 'New structural sections, headings, paragraphs, and list items.',
      significance: 'medium',
      changes: addedChanges,
      changeIds: addedChanges.map((c) => c.id),
    });
  }

  if (removedChanges.length > 0) {
    fallbackGroups.push({
      id: 'det-removed',
      topic: 'Removed Webpage Content',
      description: 'Sections, elements, and content pruned from the newer version.',
      significance: 'medium',
      changes: removedChanges,
      changeIds: removedChanges.map((c) => c.id),
    });
  }

  if (modifiedChanges.length > 0) {
    fallbackGroups.push({
      id: 'det-modified',
      topic: 'Content Modifications & Revisions',
      description: 'Text revisions, updated deadlines, and modified attributes.',
      significance: 'medium',
      changes: modifiedChanges,
      changeIds: modifiedChanges.map((c) => c.id),
    });
  }

  if (assetChanges.length > 0) {
    fallbackGroups.push({
      id: 'det-assets',
      topic: 'Technical Asset Updates',
      description: 'Stylesheet, favicon, and technical infrastructure updates.',
      significance: 'low',
      changes: assetChanges,
      changeIds: assetChanges.map((c) => c.id),
    });
  }

  return fallbackGroups.filter((g) => Array.isArray(g.changes) && g.changes.length > 0);
}
