"use client";

import React, {useEffect, useState} from "react";
import supabase from "@/lib/supabaseClient";
import {showToast} from "@/lib/toast";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

type UserRow = {
    owner_id: string;
    plan?: string | null;
    subscription_status?: string | null;
    credit_balance: number;
    updated_at?: string | null;
};

type ProjectRow = {
    id: string;
    name?: string | null;
    owner_id: string;
    created_at?: string | null;
};

export default function AdminPage() {
    // Admin UI has been removed from this project. Redirect to home.
    if (typeof window !== 'undefined') {
        window.location.replace('/');
    }
    return null;
    const [token, setToken] = useState<string | null>(null);
    const [isAdmin, setIsAdmin] = useState(false);
    const [users, setUsers] = useState<UserRow[]>([]);
    const [projects, setProjects] = useState<ProjectRow[]>([]);
    const [err, setErr] = useState<string | null>(null);

    useEffect(() => {
        let mounted = true;
        const init = async () => {
            setLoading(true);
            setErr(null);
            const {data} = await supabase.auth.getSession();
            const access = data.session?.access_token || null;
            if (!mounted) return;
            setToken(access);
            if (!access) {
                setLoading(false);
                return;
            }
            try {
                const headers = {Authorization: `Bearer ${access}`};
                const meRes = await fetch(`${API_BASE}/api/admin/me`, {headers});
                if (!meRes.ok) throw new Error("Failed to verify admin access");
                const me = await meRes.json();
                if (!mounted) return;
                if (!me?.is_admin) {
                    setIsAdmin(false);
                    setLoading(false);
                    return;
                }
                setIsAdmin(true);
                const [uRes, pRes] = await Promise.all([
                    fetch(`${API_BASE}/api/admin/users`, {headers}),
                    fetch(`${API_BASE}/api/admin/projects`, {headers}),
                ]);
                if (uRes.ok) setUsers(await uRes.json());
                if (pRes.ok) setProjects(await pRes.json());
            } catch (e: any) {
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
        await supabase.auth.signInWithOAuth({
            provider: "google",
            options: {redirectTo: window.location.origin + "/admin"}
        });
    };

    if (loading) {
        return (
            <div className="max-w-5xl mx-auto p-6">
                <div className="h-8 w-40 bg-black/5 dark:bg-white/10 rounded animate-pulse mb-4"/>
                <div className="h-32 w-full bg-black/5 dark:bg-white/10 rounded animate-pulse"/>
            </div>
        );
    }

    if (!token) {
        return (
            <div className="max-w-2xl mx-auto p-6 text-center">
                <h1 className="text-2xl font-semibold mb-3">Admin</h1>
                <p className="text-gray-600 dark:text-gray-300 mb-4">You need to sign in to continue.</p>
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

    if (!isAdmin) {
        return (
            <div className="max-w-2xl mx-auto p-6 text-center">
                <h1 className="text-2xl font-semibold mb-3">Admin</h1>
                <p className="text-gray-600 dark:text-gray-300">Your account does not have admin access.</p>
            </div>
        );
    }

    const refreshUsers = async () => {
        if (!token) return;
        const res = await fetch(`${API_BASE}/api/admin/users`, {headers: {Authorization: `Bearer ${token}`}});
        if (res.ok) setUsers(await res.json());
    };

    const refreshProjects = async () => {
        if (!token) return;
        const res = await fetch(`${API_BASE}/api/admin/projects`, {headers: {Authorization: `Bearer ${token}`}});
        if (res.ok) setProjects(await res.json());
    };

    return (
        <div className="max-w-6xl mx-auto p-6">
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-2xl font-semibold">Admin Dashboard</h1>
                <a href="/"
                   className="text-xs px-2 py-1 rounded bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15">Back
                    to app</a>
            </div>

            {err && <div className="mb-4 text-sm text-red-600">{err}</div>}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="rounded-lg border border-black/5 dark:border-white/10 p-4">
                    <div className="flex items-center justify-between mb-3">
                        <div className="text-sm font-medium">Users</div>
                        <button onClick={refreshUsers}
                                className="text-xs px-2 py-1 rounded bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15">Refresh
                        </button>
                    </div>
                    <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
                        {users.map((u) => (
                            <div key={u.owner_id} className="border border-black/5 dark:border-white/10 rounded p-3">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <div className="text-sm font-medium">{u.owner_id}</div>
                                        <div
                                            className="text-xs text-gray-600 dark:text-gray-300">Plan: {u.plan || 'free'} ·
                                            Status: {u.subscription_status || 'none'} ·
                                            Credits: {u.credit_balance}</div>
                                    </div>
                                </div>
                                <div className="mt-3 flex items-center gap-2 flex-wrap">
                                    <form
                                        onSubmit={async (e) => {
                                            e.preventDefault();
                                            if (!token) return;
                                            const form = e.currentTarget as HTMLFormElement;
                                            const input = form.elements.namedItem("delta") as HTMLInputElement;
                                            const delta = parseInt(input.value || "0", 10);
                                            if (!Number.isFinite(delta)) return;
                                            const res = await fetch(`${API_BASE}/api/admin/users/${u.owner_id}/credits`, {
                                                method: 'POST',
                                                headers: {
                                                    'Content-Type': 'application/json',
                                                    Authorization: `Bearer ${token}`
                                                },
                                                body: JSON.stringify({delta}),
                                            });
                                            if (res.ok) {
                                                showToast('Credits adjusted', 'success');
                                                input.value = "";
                                                refreshUsers();
                                            }
                                        }}
                                        className="flex items-center gap-2"
                                    >
                                        <input name="delta" type="number" placeholder="Δ credits"
                                               className="h-8 text-xs px-2 rounded border border-black/10 dark:border-white/10 bg-transparent"/>
                                        <button type="submit"
                                                className="h-8 text-xs px-2 rounded bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15">Apply
                                        </button>
                                    </form>
                                    <form
                                        onSubmit={async (e) => {
                                            e.preventDefault();
                                            if (!token) return;
                                            const form = e.currentTarget as HTMLFormElement;
                                            const select = form.elements.namedItem("plan") as HTMLSelectElement;
                                            const plan = select.value;
                                            const res = await fetch(`${API_BASE}/api/admin/users/${u.owner_id}/plan`, {
                                                method: 'POST',
                                                headers: {
                                                    'Content-Type': 'application/json',
                                                    Authorization: `Bearer ${token}`
                                                },
                                                body: JSON.stringify({plan}),
                                            });
                                            if (res.ok) {
                                                showToast('Plan updated', 'success');
                                                refreshUsers();
                                            }
                                        }}
                                        className="flex items-center gap-2"
                                    >
                                        <select name="plan" defaultValue={u.plan || 'free'}
                                                className="h-8 text-xs px-2 rounded border border-black/10 dark:border-white/10 bg-transparent">
                                            <option value="free">free</option>
                                            <option value="pro">pro</option>
                                            <option value="team">team</option>
                                            <option value="enterprise">enterprise</option>
                                            <option value="admin">admin</option>
                                        </select>
                                        <button type="submit"
                                                className="h-8 text-xs px-2 rounded bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15">Save
                                        </button>
                                    </form>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="rounded-lg border border-black/5 dark:border-white/10 p-4">
                    <div className="flex items-center justify-between mb-3">
                        <div className="text-sm font-medium">Projects</div>
                        <button onClick={refreshProjects}
                                className="text-xs px-2 py-1 rounded bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15">Refresh
                        </button>
                    </div>
                    <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
                        {projects.map((p) => (
                            <div key={p.id}
                                 className="border border-black/5 dark:border-white/10 rounded p-3 flex items-center justify-between">
                                <div>
                                    <div className="text-sm font-medium">{p.name || p.id}</div>
                                    <div className="text-xs text-gray-600 dark:text-gray-300">ID: {p.id} ·
                                        Owner: {p.owner_id}</div>
                                </div>
                                <button
                                    type="button"
                                    onClick={async () => {
                                        if (!token) return;
                                        if (!confirm('Delete this project?')) return;
                                        const res = await fetch(`${API_BASE}/api/admin/projects/${p.id}`, {
                                            method: 'DELETE',
                                            headers: {Authorization: `Bearer ${token}`}
                                        });
                                        if (res.ok) {
                                            showToast('Project deleted', 'success');
                                            refreshProjects();
                                        }
                                    }}
                                    className="text-xs px-2 py-1 rounded bg-red-600 text-white hover:bg-red-700"
                                >
                                    Delete
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="mt-6 rounded-lg border border-black/5 dark:border-white/10 p-4">
                <div className="text-sm font-medium mb-3">SEO Settings</div>
                <SeoEditor token={token}/>
            </div>
        </div>
    );
}

function SeoEditor({token}: { token: string | null }) {
    const [data, setData] = useState<any>({title: "", description: "", keywords: []});
    useEffect(() => {
        const load = async () => {
            if (!token) return;
            const res = await fetch(`${API_BASE}/api/admin/seo`, {headers: {Authorization: `Bearer ${token}`}});
            if (res.ok) setData(await res.json());
        };
        load();
    }, [token]);
    const save = async () => {
        if (!token) return;
        const res = await fetch(`${API_BASE}/api/admin/seo`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
            body: JSON.stringify(data)
        });
        if (res.ok) showToast('SEO settings saved', 'success');
    };
    return (
        <div className="space-y-3">
            <div>
                <div className="text-xs text-gray-600 dark:text-gray-300 mb-1">Title</div>
                <input value={data.title || ''} onChange={e => setData((d: any) => ({...d, title: e.target.value}))}
                       className="w-full h-8 text-sm px-2 rounded border border-black/10 dark:border-white/10 bg-transparent"/>
            </div>
            <div>
                <div className="text-xs text-gray-600 dark:text-gray-300 mb-1">Description</div>
                <textarea value={data.description || ''}
                          onChange={e => setData((d: any) => ({...d, description: e.target.value}))}
                          className="w-full h-20 text-sm p-2 rounded border border-black/10 dark:border-white/10 bg-transparent"/>
            </div>
            <div>
                <div className="text-xs text-gray-600 dark:text-gray-300 mb-1">Keywords (comma separated)</div>
                <input value={(data.keywords || []).join(', ')} onChange={e => setData((d: any) => ({
                    ...d,
                    keywords: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                }))}
                       className="w-full h-8 text-sm px-2 rounded border border-black/10 dark:border-white/10 bg-transparent"/>
            </div>
            <div>
                <button type="button" onClick={save}
                        className="inline-flex items-center justify-center font-medium rounded-md text-xs px-3 h-8 bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15 text-gray-900 dark:text-gray-100">Save
                </button>
            </div>
        </div>
    );
}
