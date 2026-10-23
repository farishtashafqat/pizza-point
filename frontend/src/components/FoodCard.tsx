import { useState } from 'react';
import type { MenuItem, MenuVariant } from '../types';

const money = (value: number) => `Rs. ${value.toLocaleString('en-PK')}`;

export default function FoodCard({ item, add }: { item: MenuItem; add: (x: MenuItem) => void }) {
  const activeVariants = item.variants?.filter((variant) => variant.is_active) ?? [];
  const [variantId, setVariantId] = useState(activeVariants[0]?.id ?? '');
  const variant = activeVariants.find((candidate) => candidate.id === variantId);
  const price = variant?.price ?? item.base_price ?? 0;
  const available = item.is_available && item.is_active;
  const isDeal = item.category?.slug === 'deals';
  const isDrink = item.category?.slug === 'drinks';
  const addItem = () => add({ ...item, price, selectedVariant: variant?.name, selectedVariantId: variant?.id });
  const updateSpotlight = (event: React.PointerEvent<HTMLElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--card-x', `${event.clientX - bounds.left}px`);
    event.currentTarget.style.setProperty('--card-y', `${event.clientY - bounds.top}px`);
  };

  return <article onPointerMove={updateSpotlight} className={'foodcard ' + (isDeal ? 'dealcard ' : '') + (isDrink ? 'drinkcard' : '')}>
    <div className={'foodart ' + (isDeal ? 'dealart ' : '') + (isDrink ? 'drinkart' : '')}>
      {item.image_url ? <img src={item.image_url} alt={item.name} /> : <span className={'foodplaceholder ' + (isDrink ? 'drinkplaceholder' : '')}>{isDrink ? <><i>PP</i><small>DRINK</small></> : 'PP'}</span>}
      <span>{available ? 'Available' : 'Unavailable'}</span>
    </div>
    <div className="foodbody">
      <div className="eyebrow">{item.category?.name}</div><h3>{item.name}</h3>
      {item.description && <p>{item.description}</p>}
      {activeVariants.length > 0 && <label className="variantlabel">Size<select value={variantId} onChange={(event) => setVariantId(event.target.value)}>{activeVariants.map((candidate: MenuVariant) => <option value={candidate.id} key={candidate.id}>{candidate.name} — {money(candidate.price)}</option>)}</select></label>}
      <div className="foodbottom"><strong>{money(price)}</strong><button className="add" onClick={addItem} disabled={!available}>+ Add</button></div>
    </div>
  </article>;
}
