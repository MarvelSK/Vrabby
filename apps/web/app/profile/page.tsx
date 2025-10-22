"use client";

import React, { useEffect, useState } from "react";
import supabase from "@/lib/supabaseClient";
import CreditsBar from "@/components/CreditsBar";
import { showToast } from "@/lib/toast";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE;

type CreditsResponse = {
  owner_id: string;
  credit_balance: number;
  subscription_status?: string | null;
  plan?: string | null;
  period_limit?: number | null;
  free_credits_on_signup?: number | null;
  tokens_per_credit?: number | null;
};

type Tx = {
  id: string;
  amount: number;
  tx_type: string;
  description?: string | null;
  created_at?: string | null;
};

export default function ProfilePage() {
  const [loading, setLoading] = useState(true);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [credits, setCredits] = useState<CreditsResponse | null>(null);
  const [txs, setTxs] = useState<Tx[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [userProfile, setUserProfile] = useState<any | null>(null);

  useEffect(() => {
    let mounted = true;

    const init = async () => {
      setLoading(true);
      setErr(null);
      const { data } = await supabase.auth.getSession();
      const access = data.session?.access_token || null;
      const email = data.session?.user?.email || null;
      if (!mounted) return;
      setSessionToken(access);
      setUserEmail(email);
      if (!access) {
        setLoading(false);
        return;
      }
      try {
        if (!API_BASE) {
          // API not configured; skip remote fetch to avoid errors in local dev.
          setLoading(false);
          return;
        }
        const headers: Record<string, string> = { Authorization: `Bearer ${access}` };
        const cRes = await fetch(`${API_BASE}/api/billing/credits`, { headers });
        if (!cRes.ok) throw new Error(`Failed to fetch credits: ${cRes.status}`);
        const cJson: CreditsResponse = await cRes.json();
        if (!mounted) return;
        setCredits(cJson);

        const tRes = await fetch(`${API_BASE}/api/billing/transactions?limit=10`, { headers });
        if (tRes.ok) {
          const tJson: Tx[] = await tRes.json();
          if (!mounted) return;
          setTxs(tJson);
        }

        // Fetch user profile snapshot/preferences
        try {
          const uRes = await fetch(`${API_BASE}/api/users/me`, { headers });
          if (uRes.ok) {
            const uJson = await uRes.json();
            if (!mounted) return;
            setUserProfile(uJson);
          }
        } catch {}
      } catch (e: any) {
        if (!mounted) return;
        setErr(e?.message || String(e));
      } finally {
        if (mounted) setLoading(false);
      }
    };

    init();

    return () => {
      mounted = false;
    };
  }, []);

  const signIn = async () => {
    await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: window.location.origin + "/profile" } });
  };

  const buyCredits = async () => {
    if (!sessionToken || !API_BASE) return;
    const res = await fetch(`${API_BASE}/api/billing/create-checkout-session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${sessionToken}`,
      },
      body: JSON.stringify({ mode: undefined }),
    });
    if (res.ok) {
      const json = await res.json();
      if (json?.url) window.location.href = json.url;
    }
  };

  const manageSubscription = async () => {
    if (!sessionToken || !API_BASE) return;
    const res = await fetch(`${API_BASE}/api/billing/create-portal-session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${sessionToken}`,
      },
      body: JSON.stringify({}),
    });
    if (res.ok) {
      const json = await res.json();
      if (json?.url) window.location.href = json.url;
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <div className="h-8 w-48 bg-black/5 dark:bg-white/10 rounded animate-pulse mb-6" />
        <div className="h-20 w-full bg-black/5 dark:bg-white/10 rounded animate-pulse" />
      </div>
    );
  }

  if (!sessionToken) {
    return (
      <div className="max-w-2xl mx-auto p-6 text-center">
        <h1 className="text-2xl font-semibold mb-3">Profile</h1>
        <p className="text-gray-600 dark:text-gray-300 mb-4">You need to sign in to view your profile.</p>
        <button
          type="button"
          onClick={signIn}
          className="inline-flex items-center justify-center font-medium rounded-md text-sm px-4 h-9 text-white bg-[#4285F4] hover:bg-[#3a75d8] transition-colors"
        >
          Sign in with Google
        </button>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl bg-white dark:bg-neutral-900 mt-10 mb-10 rounded-lg shadow-xl overflow-hidden">
        <div className="sticky top-0 z-10 flex items-center justify-between px-4 py-3 border-b border-black/5 dark:border-white/10 bg-white/80 dark:bg-neutral-900/80 backdrop-blur">
          <div className="text-base font-semibold">Profile</div>
          <a href="/" className="text-xs px-2 py-1 rounded bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/20">Close</a>
        </div>
        <div className="max-h-[80vh] overflow-y-auto px-4 py-4">
          <div className="text-gray-600 dark:text-gray-300 mb-4">{userEmail}</div>

          {err && (
            <div className="mb-4 text-sm text-red-600">{err}</div>
          )}

          <div className="rounded-lg border border-black/5 dark:border-white/10 p-4 mb-6 bg-white/50 dark:bg-neutral-900/50">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Plan</div>
              <div className="text-xs px-2 py-0.5 rounded bg-black/5 dark:bg-white/10">{credits?.plan || "free"}</div>
            </div>
            <CreditsBar balance={credits?.credit_balance || 0} periodLimit={credits?.period_limit ?? null} />
            <div className="mt-4 flex gap-3 flex-wrap">
              <button
                type="button"
                onClick={buyCredits}
                className="inline-flex items-center justify-center font-medium rounded-md text-xs px-3 h-8 text-white bg-emerald-600 hover:bg-emerald-700"
              >
                Buy credits
              </button>
              <button
                type="button"
                onClick={manageSubscription}
                className="inline-flex items-center justify-center font-medium rounded-md text-xs px-3 h-8 bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15 text-gray-900 dark:text-gray-100"
              >
                Manage subscription
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-black/5 dark:border-white/10 p-4 mb-6">
            <div className="text-sm font-medium mb-3">Recent credit activity</div>
            {txs.length === 0 ? (
              <div className="text-sm text-gray-600 dark:text-gray-300">No transactions yet.</div>
            ) : (
              <ul className="space-y-2">
                {txs.map((t) => (
                  <li key={t.id} className="flex items-center justify-between text-sm">
                    <div className="text-gray-900 dark:text-gray-100">
                      <span className={t.amount >= 0 ? "text-emerald-600" : "text-red-600"}>
                        {t.amount >= 0 ? "+" : ""}{t.amount}
                      </span>{" "}
                      <span className="uppercase text-xs bg-black/5 dark:bg-white/10 rounded px-1.5 py-0.5 ml-1">{t.tx_type}</span>
                      {t.description && <span className="ml-2 text-gray-600 dark:text-gray-300">{t.description}</span>}
                    </div>
                    <div className="text-xs text-gray-500">{t.created_at ? new Date(t.created_at).toLocaleString() : ""}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-lg border border-black/5 dark:border-white/10 p-4">
            <div className="text-sm font-medium mb-3">Privacy</div>
            <div className="flex items-center gap-3 flex-wrap">
              <button
                type="button"
                onClick={async () => {
                  if (!sessionToken) return;
                  const res = await fetch(`${API_BASE}/api/privacy/export`, { headers: { Authorization: `Bearer ${sessionToken}` } });
                  if (res.ok) {
                    const blob = new Blob([await res.text()], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'your-data.json';
                    a.click();
                    URL.revokeObjectURL(url);
                  }
                }}
                className="inline-flex items-center justify-center font-medium rounded-md text-xs px-3 h-8 bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15 text-gray-900 dark:text-gray-100"
              >
                Export my data (GDPR)
              </button>
              <button
                type="button"
                onClick={async () => {
                  if (!sessionToken) return;
                  if (!confirm('This will permanently delete your data. Continue?')) return;
                  const res = await fetch(`${API_BASE}/api/privacy/delete`, { method: 'POST', headers: { Authorization: `Bearer ${sessionToken}` } });
                  if (res.ok) {
                    showToast('Your data has been deleted. You will be signed out.', 'success');
                    await supabase.auth.signOut();
                    window.location.href = '/';
                  }
                }}
                className="inline-flex items-center justify-center font-medium rounded-md text-xs px-3 h-8 text-white bg-red-600 hover:bg-red-700"
              >
                Delete my account & data
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
