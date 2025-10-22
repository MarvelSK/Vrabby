"use client";
import React from "react";
import supabase from "@/lib/supabaseClient";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE;

export type PricingFeature = {
  id: string;
  plan_id: string;
  text: string;
  tag?: string | null;
};

export type PricingPlan = {
  id: string;
  slug?: string | null;
  name: string;
  price_eur: number;
  credits: number;
  blurb?: string | null;
  stripe_price_id?: string | null;
  is_most_popular?: boolean | null;
};

export default function PricingCard({ plan, features, onSubscribed }: { plan: PricingPlan; features: PricingFeature[]; onSubscribed?: () => void }) {
  const [loading, setLoading] = React.useState(false);

  const subscribe = async () => {
    if (!API_BASE) return; // silently ignore if backend is not configured
    try {
      setLoading(true);
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (!token) {
        // redirect to sign in
        await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: window.location.origin + "/pricing" } });
        return;
      }
      const res = await fetch(`${API_BASE}/api/billing/create-checkout-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ mode: "subscription", price_id: plan.stripe_price_id, plan: plan.slug || plan.id }),
      });
      if (res.ok) {
        const json = await res.json();
        if (json?.url) window.location.href = json.url;
        onSubscribed?.();
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`rounded-xl border border-black/5 dark:border-white/10 p-5 bg-white/50 dark:bg-black/30 backdrop-blur-sm ${plan.is_most_popular ? 'ring-2 ring-[#DE7356]' : ''}`}>
      <div className="flex items-baseline justify-between">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{plan.name}</h3>
        <div className="text-sm text-gray-500 dark:text-gray-400">{plan.credits.toLocaleString()} credits</div>
      </div>
      {plan.blurb && <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">{plan.blurb}</p>}
      <div className="mt-4">
        <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">€{plan.price_eur}</div>
        <div className="text-xs text-gray-500 dark:text-gray-400">per month</div>
      </div>
      <ul className="mt-4 space-y-2 text-sm text-gray-700 dark:text-gray-300">
        {features.map((f) => (
          <li key={f.id} className="flex items-start gap-2">
            <span className="mt-0.5 text-[#DE7356]">✓</span>
            <span>{f.text}</span>
            {f.tag && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-[#DE7356]/10 text-[#DE7356]">{f.tag}</span>}
          </li>
        ))}
      </ul>
      <button
        onClick={subscribe}
        disabled={loading || !API_BASE || !plan.stripe_price_id}
        className="mt-5 w-full inline-flex items-center justify-center h-10 text-sm font-medium rounded-md text-white bg-[#DE7356] hover:bg-[#c75f45] disabled:opacity-60"
      >
        {plan.stripe_price_id ? (loading ? "Redirecting…" : "Subscribe") : "Unavailable"}
      </button>
    </div>
  );
}
