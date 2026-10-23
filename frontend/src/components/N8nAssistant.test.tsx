// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const api=vi.hoisted(()=>({sendN8nMessage:vi.fn()}));
vi.mock('../services/n8nAssistant',()=>api);
import N8nAssistant from './N8nAssistant';

describe('N8nAssistant submission safety',()=>{
 it('does not submit the same in-flight message twice',()=>{
  let resolve!:(value:{reply:string;action:null})=>void;
  api.sendN8nMessage.mockReturnValue(new Promise(value=>{resolve=value}));
  render(<N8nAssistant open setOpen={vi.fn()} cart={[]} applyAction={()=>({ok:true,message:'',cart:[]})} applyActions={()=>({ok:true,message:'',cart:[]})}/>);
  const input=screen.getByPlaceholderText(/ask about the menu/i);
  fireEvent.change(input,{target:{value:'Hi'}});
  const form=input.closest('form')!;
  fireEvent.submit(form);fireEvent.submit(form);
  expect(api.sendN8nMessage).toHaveBeenCalledTimes(1);
  resolve({reply:'Hello!',action:null});
 });
});
