"use client";
import React, { useState } from "react";

export type FAQ = {
  id: string;
  question: string;
  answer: string;
};

export default function FAQItem({ item }: { item: FAQ }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-black/5 dark:border-white/10 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-black/5 dark:hover:bg-white/5 transition"
      >
        <span className="font-medium text-gray-900 dark:text-gray-100">{item.question}</span>
        <span className="text-gray-500 dark:text-gray-400">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-gray-700 dark:text-gray-300">
          <div dangerouslySetInnerHTML={{ __html: item.answer }} />
        </div>
      )}
    </div>
  );
}
