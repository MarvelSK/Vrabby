"use client";
import React from "react";

interface CreditsBarProps {
    balance: number;
    periodLimit?: number | null;
    className?: string;
}

export default function CreditsBar({balance, periodLimit, className}: CreditsBarProps) {
    const limit = typeof periodLimit === "number" && periodLimit > 0 ? periodLimit : null;
    const safeBalance = Math.max(0, Math.floor(balance || 0));
    const percent = limit ? Math.min(100, Math.max(0, (safeBalance / limit) * 100)) : undefined;

    return (
        <div className={className}>
            <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">Credits</div>
                <div className="text-xs text-gray-600 dark:text-gray-300">
                    {limit ? (
                        <span>{safeBalance}/{limit}</span>
                    ) : (
                        <span>{safeBalance}</span>
                    )}
                </div>
            </div>
            {limit ? (
                <div className="h-2 w-full bg-black/5 dark:bg-white/10 rounded">
                    <div
                        className="h-2 bg-emerald-500 rounded"
                        style={{width: `${percent?.toFixed(2)}%`}}
                    />
                </div>
            ) : (
                <div className="h-2 w-full bg-black/5 dark:bg-white/10 rounded">
                    <div
                        className="h-2 bg-emerald-500 rounded"
                        style={{width: `${Math.min(100, (safeBalance > 0 ? 30 : 0))}%`}}
                    />
                </div>
            )}
        </div>
    );
}
