"use client";
import React from "react";
import Link from "next/link";

export type BlogPost = {
  id: string;
  title: string;
  slug?: string | null;
  excerpt?: string | null;
  image_url?: string | null;
  created_at?: string | null;
};

export default function BlogCard({ post }: { post: BlogPost }) {
  const date = post.created_at ? new Date(post.created_at) : null;
  const href = post.slug ? `/blog/${post.slug}` : undefined;
  return (
    <article className="flex gap-4 p-3 rounded-lg border border-black/5 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
      <div className="w-36 h-24 flex-shrink-0 overflow-hidden rounded-md bg-black/5 dark:bg-white/10">
        {post.image_url ? (
          <img src={post.image_url} alt={post.title} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-xs text-gray-400">No image</div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 truncate">
          {href ? (
            <Link href={href} className="hover:underline">
              {post.title}
            </Link>
          ) : (
            post.title
          )}
        </h3>
        {post.excerpt && (
          <p className="text-sm text-gray-600 dark:text-gray-300 line-clamp-2 mt-1">{post.excerpt}</p>
        )}
        {date && (
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            {date.toLocaleDateString()}
          </div>
        )}
      </div>
    </article>
  );
}
