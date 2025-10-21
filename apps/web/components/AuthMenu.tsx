"use client";
import { useEffect, useState } from "react";
import supabase from "@/lib/supabaseClient";

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

  useEffect(() => {
    let mounted = true;

    const getSession = async () => {
      const { data } = await supabase.auth.getSession();
      const user = data.session?.user;
      if (!mounted) return;
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
        <div className="absolute right-0 mt-2 w-44 rounded-md border border-black/5 dark:border-white/10 bg-white dark:bg-neutral-900 shadow-lg py-1 text-sm">
          <div className="px-3 py-2">
            <div className="text-xs text-gray-500 dark:text-gray-400">Signed in as</div>
            <div className="text-gray-900 dark:text-gray-100 truncate">{profile.email}</div>
          </div>
          <a href="#profile" className="block px-3 py-2 hover:bg-black/5 dark:hover:bg-white/10 text-gray-900 dark:text-gray-100">Profile</a>
          <button onClick={signOut} className="w-full text-left px-3 py-2 hover:bg-black/5 dark:hover:bg-white/10 text-red-600">Sign out</button>
        </div>
      )}
    </div>
  );
}
