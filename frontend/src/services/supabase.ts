import { createClient } from '@supabase/supabase-js';
// Vite reads .env only when the dev server starts. Keep the client here so every
// component uses the same configured instance and credentials are never logged.
const url=import.meta.env.VITE_SUPABASE_URL?.trim();
const key=import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();
export const supabase = url && key ? createClient(url,key,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:true}}) : null;
export const isSupabaseConfigured=Boolean(supabase);
