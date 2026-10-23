import { describe, expect, it } from 'vitest';
import { menuSections } from './menuSections';

describe('menu sections', () => {
  it('renders the existing Drinks category in its own customer-facing group', () => {
    expect(menuSections).toContainEqual({ group: 'DRINKS', section: 'Drinks' });
  });
});
