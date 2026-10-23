// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { MenuItem } from '../types';
import CinematicDeals from './CinematicDeals';

const deal=(name:string):MenuItem=>({id:name,category_id:'deals',name,description:null,image_url:null,base_price:1000,pamphlet_section:'Deals',is_available:true,is_active:true,price:1000});

describe('CinematicDeals navigation',()=>{
  it('uses the supplied ordered array across the regular-to-Supper boundary',()=>{
    render(<CinematicDeals deals={[deal('Deal 15'),deal('Deal 16'),deal('Supper Deal 1'),deal('Supper Deal 2')]} add={vi.fn()}/>);
    expect(screen.getByRole('heading',{name:'Deal 15'})).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Show next deal'));
    expect(screen.getByRole('heading',{name:'Deal 16'})).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Show next deal'));
    expect(screen.getByRole('heading',{name:'Supper Deal 1'})).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Show previous deal'));
    expect(screen.getByRole('heading',{name:'Deal 16'})).toBeTruthy();
  });
});
