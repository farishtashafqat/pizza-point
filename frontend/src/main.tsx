import { StrictMode, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider } from './auth/AuthProvider';
import type { CartLine, MenuItem } from './types';
import { applyCartAction, applyCartActions } from './cart/actions';
import { useMenu } from './hooks/useMenu';
import './styles/global.css';

const CART_ACTION_IDS_KEY='pizza-point-cart-action-ids';
function readActionIds(){try{return new Set<string>(JSON.parse(localStorage.getItem(CART_ACTION_IDS_KEY)||'[]'))}catch{return new Set<string>()}}

function Root(){
 const [cart,setCart]=useState<CartLine[]>(()=>{try{return JSON.parse(localStorage.getItem('pizza-point-cart')||'[]')}catch{return []}});
 const cartRef=useRef(cart),appliedActionIds=useRef(readActionIds());const {items:menuItems}=useMenu();
 useEffect(()=>{cartRef.current=cart;if(cart.length)localStorage.setItem('pizza-point-cart',JSON.stringify(cart));else localStorage.removeItem('pizza-point-cart')},[cart]);
 const applyStructuredCartAction=(action:unknown)=>{const result=applyCartAction({cart:cartRef.current,menuItems,action,appliedActionIds:appliedActionIds.current});if(result.ok&&!result.duplicate){cartRef.current=result.cart;setCart(result.cart);localStorage.setItem(CART_ACTION_IDS_KEY,JSON.stringify([...appliedActionIds.current].slice(-100)))}return result};
 const applyStructuredCartActions=(actions:unknown[])=>{const result=applyCartActions({cart:cartRef.current,menuItems,actions,appliedActionIds:appliedActionIds.current});if(result.ok&&!result.duplicate){cartRef.current=result.cart;setCart(result.cart);localStorage.setItem(CART_ACTION_IDS_KEY,JSON.stringify([...appliedActionIds.current].slice(-100)))}return result};
 const add=(item:MenuItem)=>{if(!item.is_active||!item.is_available)return;setCart(old=>{const found=old.find(x=>x.id===item.id&&x.selectedVariantId===item.selectedVariantId);const next=found?old.map(x=>x.id===item.id&&x.selectedVariantId===item.selectedVariantId?{...x,quantity:Math.min(99,x.quantity+1)}:x):[...old,{...item,quantity:1}];cartRef.current=next;return next})};
 // The handler is intentionally not wired to chat text or n8n yet. A future
 // trusted bridge can call it only with a CartAction object and receive result.cart.
 return <BrowserRouter><App cart={cart} setCart={setCart} add={add} applyAction={applyStructuredCartAction} applyActions={applyStructuredCartActions}/></BrowserRouter>
}
createRoot(document.getElementById('root')!).render(<StrictMode><AuthProvider><Root /></AuthProvider></StrictMode>);
