import type { User } from '@supabase/supabase-js';
export type UserRole = 'customer' | 'kitchen' | 'admin';
export type Profile = { id:string; email:string; full_name:string; role:UserRole; is_active:boolean; created_at:string; updated_at:string };
export type AuthState = { user:User|null; profile:Profile|null; role:UserRole|null; loading:boolean; signOut:()=>Promise<void> };
