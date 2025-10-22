"use client";
import {createClient} from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL as string;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string;

import { logger } from "@/lib/logger";

if (!supabaseUrl || !supabaseAnonKey) {
    logger.warn("Supabase env vars are missing. Check NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
}

// TODO: Switch to a typed Supabase client (generated types) for safer queries
// TODO: Make schema and table access tenant-aware once multi-tenant context is available

export const supabase = createClient(supabaseUrl || "", supabaseAnonKey || "");

export default supabase;
