import { useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import type { CartLine, MenuItem } from './types';
import type { CartActionResult } from './cart/actions';
import { Navbar, Footer, Assistant, WhatsApp } from './components/Shell';
import N8nAssistant from './components/N8nAssistant';
import { Home, Menu, Cart, Login, Orders, Kitchen, Admin } from './pages';
import Deals from './pages/Deals';
import './styles/refined-hero.css';
import './styles/food-animations.css';
import ProtectedRoute from './auth/ProtectedRoute';

type Props={cart:CartLine[]; setCart:React.Dispatch<React.SetStateAction<CartLine[]>>; add:(x:MenuItem)=>void; applyAction:(action:unknown)=>CartActionResult; applyActions:(actions:unknown[])=>CartActionResult};
type ThemeChoice='light'|'dark'|'auto';
const THEME_KEY='pizza-point-theme';
const savedTheme=():ThemeChoice=>{const value=localStorage.getItem(THEME_KEY);return value==='light'||value==='dark'?value:'auto'};

export default function App({cart,setCart,add,applyAction,applyActions}:Props){
 const [chat,setChat]=useState(false),[theme,setTheme]=useState<ThemeChoice>(savedTheme),[toast,setToast]=useState('');
 const location=useLocation();const resolvedTheme=theme==='auto'?(location.pathname==='/'?'dark':'light'):theme;
 useEffect(()=>{document.documentElement.dataset.theme=resolvedTheme},[resolvedTheme]);
 useEffect(()=>{if(!toast)return;const timer=window.setTimeout(()=>setToast(''),2400);return()=>window.clearTimeout(timer)},[toast]);
 const toggleTheme=()=>{const next=resolvedTheme==='dark'?'light':'dark';setTheme(next);localStorage.setItem(THEME_KEY,next)};
 const clearUserState=()=>{setCart([]);localStorage.removeItem('pizza-point-cart');sessionStorage.removeItem('pizza-point-cart')};
 const addWithToast=(item:MenuItem)=>{add(item);setToast(`${item.name} added to your cart`)};
 const n8n=import.meta.env.VITE_N8N_ASSISTANT_ENABLED==='true';
 return <><Navbar cartCount={cart.reduce((a,x)=>a+x.quantity,0)} onLogout={clearUserState} theme={resolvedTheme} onToggleTheme={toggleTheme}/><main><Routes><Route path="/" element={<Home add={addWithToast} openAssistant={()=>setChat(true)}/>}/><Route path="/menu" element={<Menu add={addWithToast}/>}/><Route path="/deals" element={<Deals add={addWithToast}/>}/><Route path="/cart" element={<Cart cart={cart} setCart={setCart}/>}/><Route path="/orders" element={<ProtectedRoute><Orders/></ProtectedRoute>}/><Route path="/login" element={<Login/>}/><Route path="/kitchen" element={<ProtectedRoute roles={['kitchen','admin']}><Kitchen/></ProtectedRoute>}/><Route path="/admin" element={<ProtectedRoute roles={['admin']}><Admin/></ProtectedRoute>}/><Route path="*" element={<Navigate to="/"/>}/></Routes></main><Footer/><WhatsApp/>{toast&&<div className="carttoast" role="status">✓ {toast}</div>}{n8n?<N8nAssistant open={chat} setOpen={setChat} cart={cart} applyAction={applyAction} applyActions={applyActions}/>:<Assistant open={chat} setOpen={setChat}/>}</>;
}
