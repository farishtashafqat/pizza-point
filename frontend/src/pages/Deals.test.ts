import { describe, expect, it } from 'vitest';
import type { MenuItem } from '../types';
import { sortDealsNumerically } from './Deals';

const deal = (name:string):MenuItem => ({ id:name, category_id:'deals', name, description:null, image_url:null, base_price:1000, pamphlet_section:'Deals', is_available:true, is_active:true, price:1000 });

describe('deal carousel ordering', () => {
  it('shows all real regular Deals before all Supper Deals in numeric order', () => {
    const source=[...Array.from({length:16},(_,index)=>deal(`Deal ${index+1}`)),...Array.from({length:4},(_,index)=>deal(`Supper Deal ${index+1}`))].reverse();
    const names=sortDealsNumerically(source).map((item)=>item.name);
    expect(names).toEqual([...Array.from({length:16},(_,index)=>`Deal ${index+1}`),...Array.from({length:4},(_,index)=>`Supper Deal ${index+1}`)]);
    expect(names.slice(0,12)).toEqual(['Deal 1','Deal 2','Deal 3','Deal 4','Deal 5','Deal 6','Deal 7','Deal 8','Deal 9','Deal 10','Deal 11','Deal 12']);
    expect(names.slice(15,17)).toEqual(['Deal 16','Supper Deal 1']);
  });
});
