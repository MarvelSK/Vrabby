import React from "react";
import FAQItem, { FAQ } from "@/components/faq/FAQItem";
import getSupabaseServer from "@/lib/supabaseServer";

export const revalidate = 120; // refresh every 2 minutes

async function loadFAQs(): Promise<{ items: FAQ[]; error: string | null }> {
  const supabase = getSupabaseServer();
  const { data, error } = await supabase
    .from("faq_items")
    .select("id,question,answer")
    .eq("published", true)
    .order("order", { ascending: true });
  if (error) return { items: [], error: error.message };
  return { items: (data as any) || [], error: null };
}

export default async function FAQPage() {
  const { items, error } = await loadFAQs();
  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">FAQ</h1>
      {error && <div className="text-red-600">Failed to load FAQs: {error}</div>}
      {!error && items.length === 0 && (
        <div className="text-gray-600 dark:text-gray-300">No FAQs yet.</div>
      )}
      <div className="space-y-3">
        {items.map((item) => (
          <FAQItem key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
