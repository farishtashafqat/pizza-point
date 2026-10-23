import { supabase } from './supabase';
const apiUrl=import.meta.env.VITE_API_URL||'http://localhost:8000';
export type StaffMember={id:string;email:string;full_name:string;role:'admin'|'kitchen';is_active:boolean;created_at:string};
async function request(path:string,init:RequestInit={}){if(!supabase)throw new Error('Staff management is not configured.');const {data:{session}}=await supabase.auth.getSession();if(!session)throw new Error('Please sign in again.');const response=await fetch(`${apiUrl}${path}`,{...init,headers:{'Content-Type':'application/json','Authorization':`Bearer ${session.access_token}`,...init.headers}});const body=await response.json().catch(()=>null);if(!response.ok)throw new Error(typeof body?.detail==='string'?body.detail:'Unable to complete staff management request.');return body}
export const getStaff=()=>request('/staff') as Promise<StaffMember[]>;
export const inviteStaff=(input:{email:string;full_name:string;role:'admin'|'kitchen'})=>request('/staff/invite',{method:'POST',body:JSON.stringify(input)});
export const setStaffActive=(id:string,is_active:boolean)=>request(`/staff/${id}/active`,{method:'PATCH',body:JSON.stringify({is_active})});
