import React from "react";
import BlogCard, { BlogPost } from "@/components/blog/BlogCard";
import getSupabaseServer from "@/lib/supabaseServer";
import Link from "next/link";

export const revalidate = 60; // ISR: refresh content every 60s

const PAGE_SIZE = 5;

async function loadData(page: number) {
  const supabase = getSupabaseServer();
  const from = (page - 1) * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;

  const { count } = await supabase
    .from("blogs")
    .select("id", { count: "exact", head: true })
    .eq("published", true);

  const { data, error } = await supabase
    .from("blogs")
    .select("id,title,slug,excerpt,image_url,created_at")
    .eq("published", true)
    .order("created_at", { ascending: false })
    .range(from, to);

  if (error) {
    return { posts: [] as BlogPost[], total: 0, error: error.message as string };
  }

  return { posts: (data as any) || [], total: count || 0, error: null as string | null };
}

type SearchParams = Promise<{ [key: string]: string | string[] | undefined }>

export default async function BlogPage(props: { searchParams?: SearchParams }) {
  const searchParams = (await props.searchParams) || {};
  const pageParam = (searchParams?.page as string) || "1";
  const page = Math.max(1, parseInt(pageParam, 10) || 1);
  const { posts, total, error } = await loadData(page);
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">Blog</h1>

      {error && <div className="text-red-600">Failed to load blog posts: {error}</div>}

      {!error && posts.length === 0 && (
        <div className="text-gray-600 dark:text-gray-300">No posts yet.</div>
      )}

      <div className="space-y-3">
        {posts.map((p) => (
          <BlogCard key={p.id} post={p} />
        ))}
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <Link
            href={`/blog?page=${Math.max(1, page - 1)}`}
            className={`px-3 h-9 rounded-md text-sm border border-black/5 dark:border-white/10 ${page === 1 ? 'pointer-events-none opacity-50' : ''}`}
          >
            Prev
          </Link>
          <span className="text-sm text-gray-600 dark:text-gray-300">
            Page {page} of {pageCount}
          </span>
          <Link
            href={`/blog?page=${Math.min(pageCount, page + 1)}`}
            className={`px-3 h-9 rounded-md text-sm border border-black/5 dark:border-white/10 ${page === pageCount ? 'pointer-events-none opacity-50' : ''}`}
          >
            Next
          </Link>
        </div>
      )}
    </div>
  );
}
