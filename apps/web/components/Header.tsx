"use client";
import {useState} from 'react';
import ProjectSettings from '@/components/ProjectSettings';
import {usePathname} from 'next/navigation';
import Image from 'next/image';
import {useTheme} from '@/components/ThemeProvider';
import AuthMenu from "@/components/AuthMenu";
import Link from 'next/link';

export default function Header() {
    const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false);
    const pathname = usePathname();

    // Extract project ID from pathname if we're in a project page
    const projectId = pathname.match(/^\/([^\/]+)\/(chat|page)?$/)?.[1];

    // Hide header on chat pages and main page (main page has its own header)
    const isChatPage = pathname.includes('/chat');
    const isMainPage = pathname === '/';
    const theme = useTheme();

    if (isChatPage || isMainPage) {
        return null;
    }

    return (
        <header
            className="sticky top-0 z-50 backdrop-blur-xl bg-white/60 dark:bg-black/30 border-b border-black/5 dark:border-white/10">
            <div className="max-w-6xl mx-auto px-4">
                <div className="flex items-center justify-between h-14 relative">
                    {/* Left: Logo */}
                    <div className="flex items-center gap-2">
                        <img
                            src="/Vrabby_logo.svg"
                            alt="Vrabby"
                            className="h-7 w-auto select-none"
                        />
                    </div>

                    {/* Center: Navigation (absolutely centered) */}
                    <nav
                        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 hidden lg:block">
                        <ul className="flex gap-6 text-sm text-gray-500 dark:text-gray-400">
                            <li>
                                <a href="https://discord.gg/APukX5dU3D" target="_blank" rel="noopener noreferrer"
                                   className="hover:text-black dark:hover:text-white transition font-medium">
                                    Community
                                </a>
                            </li>
                            <li>
                                <Link href="/blog" className="hover:text-black dark:hover:text-white transition font-medium">
                                    Blog
                                </Link>
                            </li>
                            <li>
                                <Link href="/faq" className="hover:text-black dark:hover:text-white transition font-medium">
                                    FAQ
                                </Link>
                            </li>
                            <li>
                                <Link href="/pricing" className="hover:text-black dark:hover:text-white transition font-medium">
                                    Pricing
                                </Link>
                            </li>
                        </ul>
                    </nav>
                    {/* Right: Auth */}
                    <AuthMenu/>

                </div>

            </div>
            {/* Global Settings Modal */}
            <ProjectSettings
                isOpen={globalSettingsOpen}
                onClose={() => setGlobalSettingsOpen(false)}
                projectId="global-settings"
                projectName="Global Settings"
                initialTab="ai-assistant"
            />
        </header>
    );
}
