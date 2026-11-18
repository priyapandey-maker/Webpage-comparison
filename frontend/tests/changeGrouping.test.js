import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildTopicGroups,
  isTechnicalAsset,
  isNavigationChange,
  sanitizeTopicGroup,
  sanitizeKeyTakeaway,
} from '../src/utils/changeGrouping.js';

describe('changeGrouping unit tests', () => {
  test('empty change list returns empty array', () => {
    assert.deepEqual(buildTopicGroups([], null), []);
    assert.deepEqual(buildTopicGroups([], { topic_groups: [] }), []);
    assert.deepEqual(buildTopicGroups(null, null), []);
  });

  test('deterministic fallback when AI summary is null: all changes assigned, no duplicates', () => {
    const changes = [
      { id: 1, category: 'added', element: 'h1', description: 'Added heading' },
      { id: 2, category: 'removed', element: 'p', description: 'Removed paragraph' },
      { id: 3, category: 'modified', element: 'span', description: 'Updated text' },
      { id: 4, category: 'added', element: 'a', description: 'Added link', explanation: 'Navigation link' },
      { id: 5, category: 'modified', element: 'link', description: 'Updated stylesheet', explanation: 'Technical asset stylesheet' },
    ];

    const groups = buildTopicGroups(changes, null);
    assert.ok(groups.length > 0, 'Should produce at least one fallback group');

    // 1. All changes assigned
    const assignedIds = groups.flatMap((g) => g.changeIds);
    assert.equal(assignedIds.length, changes.length, 'Total assigned IDs must match changes length');

    // 2. No duplicates
    const uniqueIds = new Set(assignedIds);
    assert.equal(uniqueIds.size, changes.length, 'Every change ID must appear exactly once');

    // 3. Verify classification
    const assetGroup = groups.find((g) => g.id === 'det-assets');
    assert.ok(assetGroup, 'Should produce a technical asset group');
    assert.ok(assetGroup.changeIds.includes(5), 'Change 5 should be in technical assets');

    const navGroup = groups.find((g) => g.id === 'det-nav');
    assert.ok(navGroup, 'Should produce a navigation group');
    assert.ok(navGroup.changeIds.includes(4), 'Change 4 should be in navigation');
  });

  test('AI groups with valid IDs and unknown IDs ignored', () => {
    const changes = [
      { id: 10, category: 'modified', element: 'h2', description: 'Heading changed' },
      { id: 11, category: 'added', element: 'p', description: 'Paragraph added' },
      { id: 12, category: 'removed', element: 'footer', description: 'Footer removed' },
    ];

    const aiSummary = {
      executive_summary: 'Test summary',
      topic_groups: [
        {
          topic: 'Editorial Updates',
          description: 'Headings and text revisions',
          significance: 'high',
          change_ids: [10, 999], // 999 is an unknown ID
        },
        {
          topic: 'Structural Pruning',
          description: 'Removed elements',
          significance: 'medium',
          change_ids: [12],
        },
      ],
    };

    const groups = buildTopicGroups(changes, aiSummary);

    // 1. Unknown ID 999 must NOT be in any group
    const allAssignedIds = groups.flatMap((g) => g.changeIds);
    assert.ok(!allAssignedIds.includes(999), 'Unknown ID 999 must be ignored');

    // 2. All valid change IDs (10, 11, 12) must be assigned exactly once
    assert.equal(allAssignedIds.length, 3, 'Must assign exactly all 3 valid changes');
    assert.deepEqual(allAssignedIds.sort((a, b) => a - b), [10, 11, 12]);

    // 3. Change 11 (unclaimed by AI) must be in a fallback group
    const groupFor11 = groups.find((g) => g.changeIds.includes(11));
    assert.ok(groupFor11, 'Unclaimed change 11 must be preserved in a fallback group');

    // 4. No duplicate IDs
    const uniqueIds = new Set(allAssignedIds);
    assert.equal(uniqueIds.size, 3);
  });

  test('no duplicate IDs even if AI group repeats an ID across multiple groups', () => {
    const changes = [
      { id: 1, category: 'added', element: 'div', description: 'Card' },
      { id: 2, category: 'modified', element: 'p', description: 'Text' },
    ];

    const aiSummary = {
      topic_groups: [
        { topic: 'Group 1', change_ids: [1, 2] },
        { topic: 'Group 2', change_ids: [1, 2] }, // duplicate claims
      ],
    };

    const groups = buildTopicGroups(changes, aiSummary);
    const allAssignedIds = groups.flatMap((g) => g.changeIds);
    assert.equal(allAssignedIds.length, 2, 'No duplicates permitted');
    assert.equal(new Set(allAssignedIds).size, 2);
  });

  test('21-change scenario with duplicated IDs #10-#21 and missing IDs #1-#5', () => {
    // 21 actual changes matching the College Admissions comparison
    const changes = [
      { id: 1, category: 'added', element: 'List', description: 'List was added.' },
      { id: 2, category: 'added', element: 'List', description: 'List was added.' },
      { id: 3, category: 'added', element: 'Section', description: 'Section was added.' },
      { id: 4, category: 'added', element: 'Section', description: 'Section was added.' },
      { id: 5, category: 'added', element: 'Section', description: 'Section was added.' },
      { id: 6, category: 'added', element: 'Link', description: 'Link was added.', explanation: 'Start Application link' },
      { id: 7, category: 'added', element: 'Link', description: 'Link was added.', explanation: 'Download Brochure link' },
      { id: 8, category: 'added', element: 'Link', description: 'Link was added.', explanation: 'Contact Admissions link' },
      { id: 9, category: 'removed', element: 'Button', description: 'Button was removed.', explanation: 'Apply Now button' },
      { id: 10, category: 'modified', element: 'Text', description: 'Text was updated.' },
      { id: 11, category: 'modified', element: 'Paragraph', description: 'Paragraph text was updated.' },
      { id: 12, category: 'modified', element: 'Heading', description: 'Heading text was updated.' },
      { id: 13, category: 'modified', element: 'Paragraph', description: 'Paragraph text was updated.' },
      { id: 14, category: 'modified', element: 'Paragraph', description: 'Paragraph text was updated.' },
      { id: 15, category: 'modified', element: 'Heading', description: 'Heading text was updated.' },
      { id: 16, category: 'modified', element: 'Paragraph', description: 'Paragraph text was updated.' },
      { id: 17, category: 'modified', element: 'Paragraph', description: 'Paragraph text was updated.' },
      { id: 18, category: 'modified', element: 'Paragraph', description: 'Paragraph text was updated.' },
      { id: 19, category: 'modified', element: 'Heading', description: 'Heading text was updated.' },
      { id: 20, category: 'modified', element: 'Paragraph', description: 'Paragraph text was updated.' },
      { id: 21, category: 'modified', element: 'Page title', description: 'Page title text was updated.' },
    ];

    // Raw AI output from screenshot with overlapping IDs and omitted IDs #1-#5
    const aiSummary = {
      executive_summary: 'The webpage has been updated to reflect changes in the application process, scholarship information, and overall branding.',
      key_takeaways: [
        'The application process has been simplified with a new online application process.',
        'Scholarship information has been updated to include tuition fees and payment options for the 2027 application period.',
      ],
      topic_groups: [
        {
          topic: 'Content Updates',
          description: 'Changes in content such as headings, paragraphs, and links have been made.',
          significance: 'medium',
          change_ids: [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
        },
        {
          topic: 'Brand and Design',
          description: "The webpage's branding and design have been updated, including changes to the title, contact information, and dates.",
          significance: 'low',
          change_ids: [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21], // Duplicates 10-21
        },
      ],
    };

    const groups = buildTopicGroups(changes, aiSummary);

    // 1. Every detected change ID is represented
    const allAssignedIds = groups.flatMap((g) => g.changeIds);
    assert.equal(allAssignedIds.length, 21, 'All 21 change IDs must be present');

    // 2. Exactly one appearance per ID (zero duplicates)
    const uniqueIds = new Set(allAssignedIds);
    assert.equal(uniqueIds.size, 21, 'No duplicate IDs across groups');
    assert.deepEqual(
      Array.from(uniqueIds).sort((a, b) => a - b),
      Array.from({ length: 21 }, (_, i) => i + 1)
    );

    // 3. First AI group retains #10–#21
    const contentGroup = groups.find((g) => g.topic === 'Content Updates');
    assert.ok(contentGroup, 'Content Updates group should exist');
    assert.deepEqual(contentGroup.changeIds, [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]);

    // 4. Second group is deduplicated and sanitized: no longer misleadingly called 'Brand and Design'
    const navGroup = groups.find((g) => g.topic.includes('Navigation') || g.topic.includes('Action Links'));
    assert.ok(navGroup, 'Should rename Brand and Design to Navigation & Action Links for changes #6-#9');
    assert.deepEqual(navGroup.changeIds, [6, 7, 8, 9]);

    // 5. Missing changes #1–#5 are present in a fallback additions group
    const fallbackGroup = groups.find((g) => g.id.startsWith('fallback-added'));
    assert.ok(fallbackGroup, 'Should create fallback group for unassigned additions #1-#5');
    assert.deepEqual(fallbackGroup.changeIds, [1, 2, 3, 4, 5]);

    // 6. Test Key Takeaways neutralization
    const sanitizedTakeaway1 = sanitizeKeyTakeaway(aiSummary.key_takeaways[0]);
    assert.equal(
      sanitizedTakeaway1,
      'The application process has been updated with a new online application process.',
      'Must replace unsupported "simplified with" with "updated with"'
    );
    const sanitizedTakeaway2 = sanitizeKeyTakeaway(aiSummary.key_takeaways[1]);
    assert.equal(
      sanitizedTakeaway2,
      'Scholarship information has been updated to include tuition fees and payment options for the 2027 application period.'
    );
  });

  test('large change collection (1,929 changes) assigned completely with 0 duplicates', () => {
    const changes = [];
    for (let i = 1; i <= 1929; i++) {
      const cat = i % 3 === 0 ? 'added' : i % 3 === 1 ? 'removed' : 'modified';
      const isAsset = i % 10 === 0;
      const isNav = !isAsset && i % 7 === 0;

      changes.push({
        id: i,
        category: cat,
        element: isAsset ? 'link' : isNav ? 'a' : 'p',
        description: `Change ${i}`,
        explanation: isAsset ? 'Technical asset stylesheet' : isNav ? 'Navigation link' : 'Content change',
      });
    }

    // AI summary with 35 changes in 3 groups
    const aiSummary = {
      topic_groups: [
        { topic: 'Navigation Highlights', change_ids: [7, 14, 21, 28, 35], significance: 'high' },
        { topic: 'Asset Updates', change_ids: [10, 20, 30], significance: 'low' },
        { topic: 'General Editorial', change_ids: Array.from({ length: 27 }, (_, k) => k + 1).filter(id => ![7, 10, 14, 20, 21, 28, 30, 35].includes(id)), significance: 'medium' },
      ],
    };

    const groups = buildTopicGroups(changes, aiSummary);

    // 1. Verify 100% assignment
    const allAssignedIds = groups.flatMap((g) => g.changeIds);
    assert.equal(allAssignedIds.length, 1929, 'All 1,929 changes must be assigned');

    // 2. Verify 0 duplicates
    const uniqueIds = new Set(allAssignedIds);
    assert.equal(uniqueIds.size, 1929, 'All 1,929 changes must be unique');

    // 3. Every single change object is accessible
    for (const g of groups) {
      assert.equal(g.changes.length, g.changeIds.length, 'Each group changes array must match its changeIds');
    }
  });

  test('helper classification checks', () => {
    assert.ok(isTechnicalAsset({ element: 'link', explanation: 'Technical asset stylesheet' }));
    assert.ok(isTechnicalAsset({ element: 'script' }));
    assert.ok(isTechnicalAsset({ oldValue: 'rel: stylesheet' }));
    assert.ok(!isTechnicalAsset({ element: 'p', description: 'Some text' }));

    assert.ok(isNavigationChange({ element: 'a', explanation: 'Navigation destination' }));
    assert.ok(isNavigationChange({ element: 'Button', targetPath: '/html/body/header/nav/button[0]' }));
    assert.ok(isNavigationChange({ element: 'Text', targetPath: '/html/body/div/nav/ul/li/span' }));
    assert.ok(!isNavigationChange({ element: 'link', explanation: 'Technical asset stylesheet' })); // asset takes precedence
    assert.ok(!isNavigationChange({ element: 'Paragraph', targetPath: '/html/body/div/p[0]' }));
  });

  test('sanitizeKeyTakeaway filters internal schema tokens and neutralizes subjective claims', () => {
    // 1. Schema metadata tokens must be rejected
    assert.equal(sanitizeKeyTakeaway('topic_groups'), '');
    assert.equal(sanitizeKeyTakeaway('`topic_groups`'), '');
    assert.equal(sanitizeKeyTakeaway('change_ids'), '');
    assert.equal(sanitizeKeyTakeaway('executive_summary'), '');
    assert.equal(sanitizeKeyTakeaway('key_takeaways'), '');
    assert.equal(sanitizeKeyTakeaway('{"topic": "nav"}'), '');
    assert.equal(sanitizeKeyTakeaway('[]'), '');

    // 2. Subjective / speculative claims are neutralized into factual phrasing
    const claim1 = 'The main menu layout has been updated, with the main menu being moved to a sidebar and hidden.';
    const sanitized1 = sanitizeKeyTakeaway(claim1);
    assert.ok(!sanitized1.includes('being moved to a sidebar and hidden'));
    assert.ok(sanitized1.includes('menu and sidebar navigation updated'));

    const claim2 = 'The application process has been simplified with a new online system.';
    const sanitized2 = sanitizeKeyTakeaway(claim2);
    assert.ok(!sanitized2.includes('simplified with'));
    assert.ok(sanitized2.includes('updated with'));
  });

  test('buildTopicGroups never returns empty groups even if AI summary contains empty change_ids', () => {
    const changes = [
      { id: 1, category: 'modified', element: 'Heading', description: 'Updated heading' },
    ];
    const aiSummary = {
      executive_summary: 'Test summary',
      topic_groups: [
        { topic: 'Empty Group 1', description: 'No changes', change_ids: [] },
        { topic: 'Valid Group', description: 'Has change', change_ids: [1] },
        { topic: 'Empty Group 2', description: 'No changes', change_ids: [] },
      ],
    };

    const groups = buildTopicGroups(changes, aiSummary);
    assert.equal(groups.length, 1);
    assert.equal(groups[0].topic, 'Valid Group');
    assert.deepEqual(groups[0].changeIds, [1]);
  });
});
