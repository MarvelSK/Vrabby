import React from "react";
import PricingCard, { PricingFeature, PricingPlan } from "@/components/pricing/PricingCard";
import getSupabaseServer from "@/lib/supabaseServer";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE;
export const revalidate = 120; // ISR

async function loadPricing(): Promise<{ plans: PricingPlan[]; features: Record<string, PricingFeature[]>; error: string | null }> {
  try {
    const supabase = getSupabaseServer();
    const { data: plansData, error: pErr } = await supabase
      .from("pricing_plans")
      .select("id,slug,name,price_eur,credits,blurb,stripe_price_id,is_most_popular,sort")
      .eq("published", true)
      .order("sort", { ascending: true });
    if (pErr) return { plans: [], features: {}, error: pErr.message };
    const plans = (plansData as any) || [];
    if (!plans.length) return { plans, features: {}, error: null };

    const { data: featData, error: fErr } = await supabase
      .from("pricing_features")
      .select("id,plan_id,text,tag")
      .in("plan_id", plans.map((x: any) => x.id))
      .order("id", { ascending: true });
    if (fErr) return { plans, features: {}, error: fErr.message };
    const grouped: Record<string, PricingFeature[]> = {};
    for (const f of (featData as any) || []) {
      grouped[f.plan_id] = grouped[f.plan_id] || [];
      grouped[f.plan_id].push(f);
    }
    return { plans, features: grouped, error: null };
  } catch (e: any) {
    return { plans: [], features: {}, error: e?.message || "Failed to load pricing" };
  }
}

export default async function PricingPage() {
  const { plans, features, error } = await loadPricing();
  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Pricing</h1>
        <p className="mt-2 text-gray-600 dark:text-gray-300">Choose a plan that fits your workflow. Credits roll over. Cancel anytime.</p>
      </div>

      {error && (
        <div className="text-red-600 text-center">Failed to load pricing: {error}</div>
      )}

      {!error && (
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
