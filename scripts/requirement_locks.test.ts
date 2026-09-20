import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isLockableRequirementId, toLockTargets } from '../src/hooks/useArtifactLocks';
import type { RequirementPayload } from '../src/api/types';

const row = (code: string, status = 'active'): RequirementPayload => ({
  id: '2b629fbd-1492-46c3-a736-6cdd2cf9ca4a',
  requirement_code: code,
  title: code,
  status,
  user_stories: [],
});

test('lists all five saved requirements including archived rows without stories', () => {
  const input = [2, 3, 4, 5].map(n => row(`REQ-00${n}`, 'archived'));
  input.push(row('REQ-001'));
  const result = toLockTargets(input);
  assert.deepEqual(result.map(r => r.requirement_code), [
    'REQ-001', 'REQ-002', 'REQ-003', 'REQ-004', 'REQ-005',
  ]);
  assert.equal(result.filter(r => r.status === 'archived').length, 4);
  assert.ok(result.every(r => isLockableRequirementId(r.id)));
  assert.equal(input[0].requirement_code, 'REQ-002');
});

test('excludes deleted rows, not archived rows, and sorts codes numerically', () => {
  const result = toLockTargets([
    row('REQ-10'), row('REQ-1', 'ARCHIVED'), row('REQ-2'), row('REQ-3', 'DELETED'),
  ]);
  assert.deepEqual(result.map(r => r.requirement_code), ['REQ-2', 'REQ-10', 'REQ-1']);
});

test('preserves lock metadata and handles absent lists', () => {
  const result = toLockTargets([{ ...row('REQ-001'), is_locked: true, locked_by: 'owner' }]);
  assert.equal(result[0].is_locked, true);
  assert.equal(result[0].locked_by, 'owner');
  assert.deepEqual(toLockTargets(undefined), []);
  assert.deepEqual(toLockTargets(null), []);
  assert.equal(isLockableRequirementId('REQ-001'), false);
});
