import { supabase } from './supabase';
import type { CartLine } from '../types';
import type { CartAction } from '../cart/actions';
const apiUrl=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000';
export type N8nReply={reply:string;action:CartAction|null;actions?:CartAction[]};
function replyPayload(value:unknown):N8nReply{
 if(!value||typeof value!=='object')throw new Error('The assistant returned an invalid response.');
 const raw=value as Record<string,unknown>;
 if(typeof raw.reply!=='string'||!raw.reply.trim())throw new Error('The assistant returned an invalid response.');
 return {reply:raw.reply,action:(raw.action&&typeof raw.action==='object'?raw.action as CartAction:null),actions:Array.isArray(raw.actions)?raw.actions as CartAction[]:[]};
}
export async function sendN8nMessage(message:string,messageId:string,cart:CartLine[],history:{role:'customer'|'assistant';content:string}[]):Promise<N8nReply>{
 if(!supabase)throw new Error('The customer app is not configured.');const {data:{session}}=await supabase.auth.getSession();if(!session)throw new Error('Please sign in to use the assistant.');
 const response=await fetch(`${apiUrl}/assistant/n8n/messages`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${session.access_token}`},body:JSON.stringify({message,message_id:messageId,cart:cart.map(x=>({item_id:x.id,variant_id:x.selectedVariantId||null,quantity:x.quantity})),history:history.slice(-8).map(x=>({role:x.role,content:x.content.slice(0,500)}))})});
 const payload=await response.json().catch(()=>({}));if(!response.ok)throw new Error(typeof payload.detail==='string'?payload.detail:'The assistant is temporarily unavailable.');return replyPayload(payload);
}
