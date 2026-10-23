// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import MarkdownMessage from './MarkdownMessage';
describe('MarkdownMessage',()=>{
 it('renders escaped newlines, bold text, and lists without interpreting HTML',()=>{render(<MarkdownMessage content={'**Fresh**\\n- Pizza\\n- Fries\\n<script>alert(1)</script>'}/>);expect(screen.getByText('Fresh').tagName).toBe('STRONG');expect(screen.getByRole('list')).toBeTruthy();expect(screen.getByText('<script>alert(1)</script>')).toBeTruthy();expect(document.querySelector('script')).toBeNull()});
 it('renders markdown tables',()=>{render(<MarkdownMessage content={'| Item | Price |\n| --- | --- |\n| Pizza | Rs. 500 |'}/>);expect(screen.getByRole('table')).toBeTruthy();expect(screen.getByText('Rs. 500')).toBeTruthy()});
 it('decodes safe HTML entities as text without interpreting HTML',()=>{render(<MarkdownMessage content={'Pizza&#x20;Point &amp; &lt;safe&gt;'}/>);expect(screen.getByText('Pizza Point & <safe>')).toBeTruthy();expect(document.querySelector('safe')).toBeNull()});
});
