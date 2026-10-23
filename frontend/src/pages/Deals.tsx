import { useMemo } from 'react';
import type { MenuItem } from '../types';
import { useMenu } from '../hooks/useMenu';
import CinematicDeals from '../components/CinematicDeals';

const dealNumber=(name:string)=>Number(name.match(/\bdeal\s*(\d+)\b/i)?.[1]??name.match(/\d+/)?.[0]??Number.MAX_SAFE_INTEGER);
const dealGroup=(name:string)=>/\b(?:super|supper)\s+deal\b/i.test(name)?1:0;

export const sortDealsNumerically=(items:MenuItem[])=>[...items].sort((left,right)=>dealGroup(left.name)-dealGroup(right.name)||dealNumber(left.name)-dealNumber(right.name)||left.name.localeCompare(right.name,undefined,{numeric:true,sensitivity:'base'}));

export default function Deals({add}:{add:(item:MenuItem)=>void}){const {items,loading,error}=useMenu();const deals=useMemo(()=>sortDealsNumerically(items.filter(item=>item.category?.slug==='deals')),[items]);if(loading)return <div className="deals-loading">Loading Pizza Point deals…</div>;if(error)return <div className="deals-loading">{error}</div>;return <CinematicDeals deals={deals} add={add}/>}
