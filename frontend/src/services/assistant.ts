import { supabase } from './supabase';

const apiUrl=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000';
export type AssistantLine={item_id:string;name:string;category:string;variant:string|null;variant_id:string|null;quantity:number;unit_price:number;subtotal:number};
export type AssistantState={reply:string;draft:{items:AssistantLine[];total:number;count:number};pending:unknown;order_type:string|null;delivery_address:string|null;messages:{role:'customer'|'assistant';content:string;created_at:string}[]};
async function request(path:string,init?:RequestInit){if(!supabase)throw new Error('The customer app is not configured.');const {data}=await supabase.auth.getSession();if(!data.session)throw new Error('Please sign in to use the ordering assistant.');const response=await fetch(`${apiUrl}${path}`,{...init,headers:{'Content-Type':'application/json',Authorization:`Bearer ${data.session.access_token}`,...init?.headers}});const payload=await response.json().catch(()=>({}));if(!response.ok)throw new Error(typeof payload.detail==='string'?payload.detail:'The assistant is temporarily unavailable.');return payload as AssistantState}
export const getAssistantState=()=>request('/assistant/state');
export const resetAssistant=()=>request('/assistant/reset',{method:'POST'});
export const sendAssistantMessage=(message:string,message_id:string)=>request('/assistant/messages',{method:'POST',body:JSON.stringify({message,message_id})});
