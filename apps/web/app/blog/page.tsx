"use client";
import React, { useEffect, useMemo, useState } from "react";
import supabase from "@/lib/supabaseClient";
import BlogCard, { BlogPost } from "@/components/blog/BlogCard";
import { useSearchParams, useRouter } from "next/navigation";

const PAGE_SIZE = 5;

export default function BlogPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));

  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const from = (page - 1) * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        // Count total published posts
        const { count } = await supabase
          .from("blogs")
          .select("id", { count: "exact", head: true })
          .eq("published", true);
        if (!cancelled) setTotal(count || 0);

        const { data, error } = await supabase
          .from("blogs")
          .select("id,title,slug,excerpt,image_url,created_at")
          .eq("published", true)
          .order("created_at", { ascending: false })
          .range(from, to);
        if (error) throw error;
        if (!cancelled) setPosts((data as any) || []);
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
  }, [page, refreshTick]);

  // Realtime updates: refetch on any change to published blogs
  useEffect(() => {
    const channel = supabase
      .channel("realtime:blogs")
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'blogs' },
        () => setRefreshTick((x) => x + 1)
      )
      .subscribe();
    return () => {
      try { supabase.removeChannel(channel); } catch {}
    };
  }, []);

  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total]);

  const goPage = (p: number) => {
    const newParams = new URLSearchParams(Array.from(searchParams.entries()));
    newParams.set("page", String(p));
    router.push(`/blog?${newParams.toString()}`);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">Blog</h1>
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: PAGE_SIZE }).map((_, i) => (
            <div key={i} className="h-28 rounded-lg bg-black/5 dark:bg-white/10 animate-pulse" />
          ))}
        </div>
      )}
      {!loading && error && (
        <div className="text-red-600">Failed to load blog posts: {error}</div>
      )}
      {!loading && !error && posts.length === 0 && (
        <div className="text-gray-600 dark:text-gray-300">No posts yet.</div>
      )}
      <div className="space-y-3">
        {posts.map((p) => (
          <BlogCard key={p.id} post={p} />
        ))}
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => goPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="px-3 h-9 rounded-md text-sm border border-black/5 dark:border-white/10 disabled:opacity-50"
          >
            Prev
          </button>
          <span className="text-sm text-gray-600 dark:text-gray-300">
            Page {page} of {pageCount}
          </span>
          <button
            onClick={() => goPage(Math.min(pageCount, page + 1))}
            disabled={page === pageCount}
            className="px-3 h-9 rounded-md text-sm border border-black/5 dark:border-white/10 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
