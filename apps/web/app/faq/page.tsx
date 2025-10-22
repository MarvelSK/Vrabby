"use client";
import React, { useEffect, useState } from "react";
import supabase from "@/lib/supabaseClient";
import FAQItem, { FAQ } from "@/components/faq/FAQItem";

export default function FAQPage() {
  const [items, setItems] = useState<FAQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const { data, error } = await supabase
          .from("faq_items")
          .select("id,question,answer")
          .eq("published", true)
          .order("order", { ascending: true });
        if (error) throw error;
        if (!cancelled) setItems((data as any) || []);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [refreshTick]);

  useEffect(() => {
    const channel = supabase
      .channel("realtime:faq")
      .on('postgres_changes', { event: '*', schema: 'public', table: 'faq_items' }, () => setRefreshTick((x) => x + 1))
      .subscribe();
    return () => { try { supabase.removeChannel(channel); } catch {} };
  }, []);

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">FAQ</h1>
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-16 rounded-lg bg-black/5 dark:bg-white/10 animate-pulse" />
          ))}
        </div>
      )}
      {!loading && error && <div className="text-red-600">Failed to load FAQs: {error}</div>}
      {!loading && !error && items.length === 0 && (
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
