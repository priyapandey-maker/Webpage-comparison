import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { getAiStatusInfo } from '../src/utils/aiStatus.js';

describe('aiStatus mapping and panel info tests', () => {
  test('returns busy status info when aiStatus is "busy"', () => {
    const info = getAiStatusInfo('busy');
    assert.equal(info.pill, 'AI Busy');
    assert.equal(info.title, 'AI Service Busy');
    assert.ok(info.desc.includes('busy processing another comparison'));
  });

  test('returns timeout status info when aiStatus is "timeout"', () => {
    const info = getAiStatusInfo('timeout');
    assert.equal(info.pill, 'AI Timeout');
    assert.equal(info.title, 'AI Generation Timed Out');
    assert.ok(info.desc.includes('90-second processing limit'));
  });

  test('returns invalid_response status info when aiStatus is "invalid_response"', () => {
    const info = getAiStatusInfo('invalid_response');
    assert.equal(info.pill, 'AI Response Incomplete');
    assert.equal(info.title, 'AI Summary Incomplete');
    assert.ok(info.desc.includes('incomplete or invalid'));
  });

  test('returns unavailable status info for "unavailable" or null/undefined', () => {
    const info1 = getAiStatusInfo('unavailable');
    assert.equal(info1.pill, 'AI Unavailable');
    assert.equal(info1.title, 'AI Summary Not Generated');
    assert.ok(info1.desc.includes('disabled, offline, or timed out'));

    const info2 = getAiStatusInfo(null);
    assert.equal(info2.pill, 'AI Unavailable');
    assert.equal(info2.title, 'AI Summary Not Generated');

    const info3 = getAiStatusInfo(undefined);
    assert.equal(info3.pill, 'AI Unavailable');

    const info4 = getAiStatusInfo('unknown_status');
    assert.equal(info4.pill, 'AI Unavailable');
  });
});
