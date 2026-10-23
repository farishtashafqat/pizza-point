import { useEffect, useState } from 'react';
import type { MenuItem } from '../types';

const money = (value: number) => `Rs. ${value.toLocaleString('en-PK')}`;

export default function CinematicDeals({ deals, add }: { deals: MenuItem[]; add: (item: MenuItem) => void }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [direction, setDirection] = useState<'next' | 'previous'>('next');
  useEffect(() => setActiveIndex((index) => Math.min(index, Math.max(deals.length - 1, 0))), [deals.length]);
  if (!deals.length) return <div className="deals-empty"><h1>Deals are being prepared.</h1><p>Check back soon for Pizza Point’s current offers.</p></div>;
  const deal = deals[activeIndex];
  const changeDeal = (step: number) => { setDirection(step > 0 ? 'next' : 'previous'); setActiveIndex((index) => (index + step + deals.length) % deals.length); };
  return <section className="deals-page"><div className="wrap deals-shell"><div className="deals-heading"><span className="tag">PIZZA POINT DEALS</span><h1>Good food,<br/><mark>better together.</mark></h1></div><div className="deals-carousel" aria-roledescription="carousel" aria-label="Pizza Point deals"><button className="deal-arrow previous" onClick={() => changeDeal(-1)} aria-label="Show previous deal">←</button><article className={`deal-panel ${direction}`} key={deal.id}><div className="deal-panel-copy"><span className="deal-count">{String(activeIndex + 1).padStart(2, '0')} / {String(deals.length).padStart(2, '0')}</span><h2>{deal.name}</h2><p>{deal.description || 'A complete Pizza Point deal, prepared for your table.'}</p><strong>{money(deal.base_price ?? deal.price)}</strong><button className="btn" onClick={() => add(deal)} disabled={!deal.is_active || !deal.is_available}>{deal.is_active && deal.is_available ? '+ Add deal to cart' : 'Currently unavailable'}</button></div><div className="deal-panel-visual"><img src={deal.image_url || '/menu/items/pizza-chicken-tikka.png'} alt={deal.name}/></div></article><button className="deal-arrow next" onClick={() => changeDeal(1)} aria-label="Show next deal">→</button></div><div className="deal-dots" role="tablist" aria-label="Choose a deal">{deals.map((item, index) => <button key={item.id} className={index === activeIndex ? 'active' : ''} onClick={() => { setDirection(index > activeIndex ? 'next' : 'previous'); setActiveIndex(index); }} aria-label={`Show ${item.name}`} aria-selected={index === activeIndex} role="tab"/>)}</div></div></section>;
}
