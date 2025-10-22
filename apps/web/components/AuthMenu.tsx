"use client";
import { useEffect, useState } from "react";
import supabase from "@/lib/supabaseClient";
import CreditsBar from "@/components/CreditsBar";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE;

type CreditsResponse = {
  credit_balance: number;
  period_limit?: number | null;
  plan?: string | null;
};

interface Profile {
  id: string;
  email?: string;
  name?: string;
  avatar_url?: string;
}

export default function AuthMenu() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);
  const [credits, setCredits] = useState<CreditsResponse | null>(null);
  const [loadingCredits, setLoadingCredits] = useState(false);

  useEffect(() => {
    let mounted = true;

    const getSession = async () => {
      const { data } = await supabase.auth.getSession();
      const user = data.session?.user;
      if (!mounted) return;
      if (user) {
        const newProfile: Profile = {
          id: user.id,
          email: user.email ?? undefined,
          name: (user.user_metadata?.name as string) || (user.user_metadata?.full_name as string) || undefined,
          avatar_url:
            (user.user_metadata?.avatar_url as string) ||
            (user.user_metadata?.picture as string) ||
            undefined,
        };
        setProfile(newProfile);
        // Notify backend of login event and snapshot profile
        try {
          if (API_BASE) {
            const token = (await supabase.auth.getSession()).data.session?.access_token;
            if (token) {
              await fetch(`${API_BASE}/api/users/events`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ event: 'login', email: newProfile.email, name: newProfile.name, avatar_url: newProfile.avatar_url }),
              });
            }
          }
        } catch {}
      } else {
        setProfile(null);
      }
      setLoading(false);
    };

    getSession();

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      const user = session?.user;
      if (user) {
        setProfile({
          id: user.id,
          email: user.email ?? undefined,
          name: (user.user_metadata?.name as string) || (user.user_metadata?.full_name as string) || undefined,
          avatar_url:
            (user.user_metadata?.avatar_url as string) ||
            (user.user_metadata?.picture as string) ||
            undefined,
        });
      } else {
        setProfile(null);
      }
    });

    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  // Load credits when menu opens
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!menuOpen || !profile?.id) return;
      try {
        setLoadingCredits(true);
        const { data } = await supabase.auth.getSession();
        const token = data.session?.access_token;
        if (!token) return;
        if (!API_BASE) return;
        const res = await fetch(`${API_BASE}/api/billing/credits`, { headers: { Authorization: `Bearer ${token}` } });
        if (!cancelled && res.ok) {
          const json: CreditsResponse = await res.json();
          setCredits(json);
        }
      } catch {
        // ignore
      } finally {
        if (!cancelled) setLoadingCredits(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [menuOpen, profile?.id]);

  const signIn = async () => {
    // Prefer Google OAuth if configured. You can add more providers as needed.
    await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: "http://localhost:3000/" } });
  };

  const signOut = async () => {
    await supabase.auth.signOut();
    setMenuOpen(false);
  };

  if (loading) {
    return (
      <div className="items-center gap-3 hidden lg:flex">
        <div className="h-8 w-24 bg-black/5 dark:bg-white/10 rounded-md animate-pulse" />
        <div className="h-8 w-28 bg-[#4285F4]/70 rounded-md animate-pulse" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="items-center gap-3 hidden lg:flex">
        <button
          type="button"
          onClick={signIn}
          className="flex items-center justify-center font-medium shrink-0 rounded-md text-xs px-3 h-8
    bg-black/[0.05] dark:bg-white/[0.05]
    text-gray-900 dark:text-gray-100
    hover:bg-black/[0.08] dark:hover:bg-white/[0.1]
    transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#4285F4]/50"
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={signIn}
          className="flex items-center justify-center font-medium shrink-0 rounded-md text-xs px-3 h-8
    text-white bg-[#4285F4]
    hover:bg-[#3a75d8] active:bg-[#356acc]
    transition-colors duration-200 shadow-sm
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#4285F4]/50"
        >
          Get started
        </button>
      </div>
    );
  }

  return (
    <div className="relative hidden lg:block">
      <button
        type="button"
        onClick={() => setMenuOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md h-8 pl-1 pr-2 text-xs bg-black/[0.05] dark:bg-white/[0.05] hover:bg-black/[0.08] dark:hover:bg-white/[0.1] transition-colors"
      >
        <div className="h-7 w-7 rounded-full overflow-hidden bg-black/10 dark:bg-white/10">
          {profile.avatar_url ? (
            <img src={profile.avatar_url} alt={profile.name || profile.email || "Profile"} className="h-full w-full object-cover" />
          ) : (
            <div className="h-full w-full flex items-center justify-center text-[10px] font-semibold">
              {(profile.name || profile.email || "?").slice(0, 1).toUpperCase()}
            </div>
          )}
        </div>
        <span className="text-gray-900 dark:text-gray-100 font-medium truncate max-w-[140px]">
          {profile.name || profile.email}
        </span>
      </button>

      {menuOpen && (
        <div className="absolute right-0 mt-2 w-60 rounded-md border border-black/5 dark:border-white/10 bg-white dark:bg-neutral-900 shadow-lg py-1 text-sm">
          <div className="px-3 pt-3 pb-2 border-b border-black/5 dark:border-white/10">
            <div className="flex items-center justify-between mb-1">
              <div className="text-xs text-gray-500 dark:text-gray-400">Plan</div>
              <div className="text-xs font-medium text-gray-900 dark:text-gray-100">{credits?.plan || "free"}</div>
            </div>
            <div className="mt-1">
              <CreditsBar balance={credits?.credit_balance || 0} periodLimit={credits?.period_limit ?? null} />
            </div>
          </div>
          <div className="px-3 py-2">
            <div className="text-xs text-gray-500 dark:text-gray-400">Signed in as</div>
            <div className="text-gray-900 dark:text-gray-100 truncate">{profile.email}</div>
          </div>
          <Link href="/profile" className="block px-3 py-2 hover:bg-black/5 dark:hover:bg-white/10 text-gray-900 dark:text-gray-100">Profile</Link>
          <button onClick={signOut} className="w-full text-left px-3 py-2 hover:bg-black/5 dark:hover:bg-white/10 text-red-600">Sign out</button>
        </div>
      )}
    </div>
  );
}
