"use client";
import React, { useEffect, useMemo, useState } from "react";
import supabase from "@/lib/supabaseClient";
import PricingCard, { PricingFeature, PricingPlan } from "@/components/pricing/PricingCard";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE;

export default function PricingPage() {
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [features, setFeatures] = useState<Record<string, PricingFeature[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const { data: plansData, error: pErr } = await supabase
          .from("pricing_plans")
          .select("id,slug,name,price_eur,credits,blurb,stripe_price_id,is_most_popular,sort")
          .eq("published", true)
          .order("sort", { ascending: true });
        if (pErr) throw pErr;
        const pp = (plansData as any) || [];
        if (!cancelled) setPlans(pp);

        if (pp.length) {
          const { data: featData, error: fErr } = await supabase
            .from("pricing_features")
            .select("id,plan_id,text,tag")
            .in("plan_id", pp.map((x: any) => x.id))
            .order("id", { ascending: true });
          if (fErr) throw fErr;
          const grouped: Record<string, PricingFeature[]> = {};
          for (const f of (featData as any) || []) {
            grouped[f.plan_id] = grouped[f.plan_id] || [];
            grouped[f.plan_id].push(f);
          }
          if (!cancelled) setFeatures(grouped);
        } else {
          if (!cancelled) setFeatures({});
        }
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
      .channel("realtime:pricing")
      .on('postgres_changes', { event: '*', schema: 'public', table: 'pricing_plans' }, () => setRefreshTick((x) => x + 1))
      .on('postgres_changes', { event: '*', schema: 'public', table: 'pricing_features' }, () => setRefreshTick((x) => x + 1))
      .subscribe();
    return () => { try { supabase.removeChannel(channel); } catch {} };
  }, []);

  const mostPopular = useMemo(() => plans.find((p) => p.is_most_popular), [plans]);

  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Pricing</h1>
        <p className="mt-2 text-gray-600 dark:text-gray-300">Choose a plan that fits your workflow. Credits roll over. Cancel anytime.</p>
      </div>

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-64 rounded-xl bg-black/5 dark:bg-white/10 animate-pulse" />
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="text-red-600 text-center">Failed to load pricing: {error}</div>
      )}

      {!loading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {plans.map((plan) => (
            <PricingCard key={plan.id} plan={plan} features={features[plan.id] || []} />
          ))}
        </div>
      )}

      {!API_BASE && (
        <p className="mt-6 text-center text-xs text-amber-600">
          Note: API_BASE is not configured; Subscribe button will be disabled in local frontend-only mode.
        </p>
      )}
    </div>
  );
}
