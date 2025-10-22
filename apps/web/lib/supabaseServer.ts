import { createClient } from "@supabase/supabase-js";

// Server-side Supabase client for RSC/ISR usage
// Uses the public anon key (read-only) and is safe to use on the server.
// TODO: If per-tenant schemas are introduced, construct client with tenant-aware options here.

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL as string | undefined;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string | undefined;

if (!supabaseUrl || !supabaseAnonKey) {
  // Avoid throwing on build; pages can handle missing config gracefully
  // eslint-disable-next-line no-console
  console.warn("Supabase server client missing config. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
}

export function getSupabaseServer() {
  return createClient(supabaseUrl || "", supabaseAnonKey || "");
}

export default getSupabaseServer;
