"use client";
import {useEffect, useState, useRef} from "react";
import {motion} from "framer-motion";
import {useRouter} from "next/navigation";
import GlobalSettings from "@/components/GlobalSettings";
import {useGlobalSettings} from "@/contexts/GlobalSettingsContext";
import Image from "next/image";
import {Image as ImageIcon} from "lucide-react";
import {MotionDiv} from "@/lib/motion";
import AuthMenu from "@/components/AuthMenu";


// Ensure fetch is available
const fetchAPI = globalThis.fetch || fetch;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

type Project = {
    id: string;
    name: string;
    status?: string;
    preview_url?: string | null;
    created_at: string;
    last_active_at?: string | null;
    last_message_at?: string | null;
    initial_prompt?: string | null;
    preferred_cli?: string | null;
    selected_model?: string | null;
    services?: {
        github?: { connected: boolean; status: string };
        supabase?: { connected: boolean; status: string };
        vercel?: { connected: boolean; status: string };
    };
};

// Brand color accent used in subtle gradient glow
const assistantBrandColors: { [key: string]: string } = {
    claude: "#4285F4",
    cursor: "#4285F4",
    qwen: "#4285F4",
    gemini: "#4285F4",
    codex: "#4285F4",
};

export default function HomePage() {
    const [projects, setProjects] = useState<Project[]>([]);
    const [showCreate, setShowCreate] = useState(false);
    const [showGlobalSettings, setShowGlobalSettings] = useState(false);
    const [globalSettingsTab, setGlobalSettingsTab] =
        useState<"general" | "ai-assistant">("ai-assistant");
    const [editingProject, setEditingProject] = useState<Project | null>(null);
    const [deleteModal, setDeleteModal] = useState<{
        isOpen: boolean;
        project: Project | null;
    }>({isOpen: false, project: null});
    const [isDeleting, setIsDeleting] = useState(false);
    const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
    const [prompt, setPrompt] = useState("");
    const [selectedAssistant, setSelectedAssistant] = useState("claude");
    const [selectedModel, setSelectedModel] = useState("claude-sonnet-4.5");
    const [usingGlobalDefaults, setUsingGlobalDefaults] = useState(true);
    const [cliStatus, setCLIStatus] = useState<{
        [key: string]: { installed: boolean; checking: boolean; version?: string; error?: string };
    }>({});
    const [isInitialLoad, setIsInitialLoad] = useState(true);

    // Models per assistant
    const modelsByAssistant = {
        claude: [
            {id: "claude-sonnet-4.5", name: "Claude Sonnet 4.5"},
            {id: "claude-haiku-4.5", name: "Claude Haiku 4.5"},
        ],
        cursor: [
            {id: "gpt-5", name: "GPT-5"},
            {id: "claude-sonnet-4.5", name: "Claude Sonnet 4.5"},
            {id: "claude-opus-4.1", name: "Claude Opus 4.1"},
        ],
        codex: [{id: "gpt-5", name: "GPT-5"}],
        qwen: [{id: "qwen3-coder-plus", name: "Qwen3 Coder Plus"}],
        gemini: [
            {id: "gemini-2.5-pro", name: "Gemini 2.5 Pro"},
            {id: "gemini-2.5-flash", name: "Gemini 2.5 Flash"},
        ],
    };
    const availableModels =
        modelsByAssistant[selectedAssistant as keyof typeof modelsByAssistant] || [];

    // Global settings
    const {settings: globalSettings} = useGlobalSettings();

    const [logos, setLogos] = useState<string[]>([]);

    useEffect(() => {
        setLogos([
            "google.webp",
            "stripe.webp",
            "supabase.webp",
            "intel.webp",
            "github.webp",
        ]);
    }, []);

    // Initial selection behavior
    useEffect(() => {
        const isPageRefresh = !sessionStorage.getItem("navigationFlag");
        if (isPageRefresh) {
            sessionStorage.setItem("navigationFlag", "true");
            setIsInitialLoad(true);
            setUsingGlobalDefaults(true);
        } else {
            const storedAssistant = sessionStorage.getItem("selectedAssistant");
            const storedModel = sessionStorage.getItem("selectedModel");
            if (storedAssistant && storedModel) {
                setSelectedAssistant(storedAssistant);
                setSelectedModel(storedModel);
                setUsingGlobalDefaults(false);
                setIsInitialLoad(false);
                return;
            }
        }
    }, []);

    useEffect(() => {
        const handleBeforeUnload = () => {
            sessionStorage.removeItem("navigationFlag");
        };
        window.addEventListener("beforeunload", handleBeforeUnload);
        return () => window.removeEventListener("beforeunload", handleBeforeUnload);
    }, []);

    useEffect(() => {
        if (!usingGlobalDefaults || !isInitialLoad) return;
        const cli = globalSettings?.default_cli || "claude";
        setSelectedAssistant(cli);
        const modelFromGlobal = globalSettings?.cli_settings?.[cli]?.model;
        if (modelFromGlobal) {
            setSelectedModel(modelFromGlobal);
        } else {
            if (cli === "claude") setSelectedModel("claude-sonnet-4.5");
            else if (cli === "cursor") setSelectedModel("gpt-5");
            else if (cli === "codex") setSelectedModel("gpt-5");
            else if (cli === "qwen") setSelectedModel("qwen3-coder-plus");
            else if (cli === "gemini") setSelectedModel("gemini-2.5-pro");
        }
    }, [globalSettings, usingGlobalDefaults, isInitialLoad]);

    useEffect(() => {
        if (!isInitialLoad && selectedAssistant && selectedModel) {
            sessionStorage.setItem("selectedAssistant", selectedAssistant);
            sessionStorage.setItem("selectedModel", selectedModel);
        }
    }, [selectedAssistant, selectedModel, isInitialLoad]);

    // UI state
    const [showAssistantDropdown, setShowAssistantDropdown] = useState(false);
    const [showModelDropdown, setShowModelDropdown] = useState(false);
    const [isCreatingProject, setIsCreatingProject] = useState(false);
    const [uploadedImages, setUploadedImages] = useState<
        { id: string; name: string; url: string; path: string; file?: File }[]
    >([]);
    const [isUploading, setIsUploading] = useState(false);
    const [isDragOver, setIsDragOver] = useState(false);

    const router = useRouter();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const assistantDropdownRef = useRef<HTMLDivElement>(null);
    const modelDropdownRef = useRef<HTMLDivElement>(null);

    // CLI installation status
    useEffect(() => {
        const checkCLIStatus = async () => {
            const checkingStatus: { [key: string]: { installed: boolean; checking: boolean } } = {};
            assistantOptions.forEach((cli) => {
                checkingStatus[cli.id] = {installed: false, checking: true};
            });
            setCLIStatus(checkingStatus);

            try {
                const response = await fetch(`${API_BASE}/api/settings/cli-status`);
                if (response.ok) {
                    const data = await response.json();
                    setCLIStatus(data);
                } else {
                    const fallbackStatus: {
                        [key: string]: { installed: boolean; checking: boolean; error: string };
                    } = {};
                    assistantOptions.forEach((cli) => {
                        fallbackStatus[cli.id] = {
                            installed: cli.id === "claude" || cli.id === "cursor" || cli.id === "codex",
                            checking: false,
                            error: "Unable to check installation status",
                        };
                    });
                    setCLIStatus(fallbackStatus);
                }
            } catch {
                const errorStatus: {
                    [key: string]: { installed: boolean; checking: boolean; error: string };
                } = {};
                assistantOptions.forEach((cli) => {
                    errorStatus[cli.id] = {
                        installed: cli.id === "claude" || cli.id === "cursor" || cli.id === "codex",
                        checking: false,
                        error: "Network error",
                    };
                });
                setCLIStatus(errorStatus);
            }
        };

        checkCLIStatus();
    }, []);

    // Click-outside close
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (assistantDropdownRef.current && !assistantDropdownRef.current.contains(event.target as Node)) {
                setShowAssistantDropdown(false);
            }
            if (modelDropdownRef.current && !modelDropdownRef.current.contains(event.target as Node)) {
                setShowModelDropdown(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    // Utilities
    const formatTime = (dateString: string | null) => {
        if (!dateString) return "Never";
        let utcDateString = dateString;
        const hasTimezone =
            dateString.endsWith("Z") || dateString.includes("+") || dateString.match(/[-+]\d{2}:\d{2}$/);
        if (!hasTimezone) utcDateString = dateString + "Z";

        const date = new Date(utcDateString);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMins = Math.floor(diffMs / (1000 * 60));
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return "Just now";
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 30) return `${diffDays}d ago`;

        return date.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
        });
    };

    const getInitials = (name: string) =>
        name
            .split(" ")
            .map((w) => w[0])
            .join("")
            .slice(0, 2)
            .toUpperCase();

    // Data
    async function load() {
        try {
            const r = await fetchAPI(`${API_BASE}/api/projects`);
            if (r.ok) {
                const projectsData = await r.json();
                const sortedProjects = projectsData.sort((a: Project, b: Project) => {
                    const aTime = a.last_message_at || a.created_at;
                    const bTime = b.last_message_at || b.created_at;
                    return new Date(bTime).getTime() - new Date(aTime).getTime();
                });
                setProjects(sortedProjects);
            }
        } catch (error) {
            console.error("Failed to load projects:", error);
        }
    }

    async function onCreated() {
        await load();
    }

    const showToast = (message: string, type: "success" | "error") => {
        setToast({message, type});
        setTimeout(() => setToast(null), 4000);
    };

    const openDeleteModal = (project: Project) => {
        setDeleteModal({isOpen: true, project});
    };
    const closeDeleteModal = () => setDeleteModal({isOpen: false, project: null});

    async function deleteProject() {
        if (!deleteModal.project) return;
        setIsDeleting(true);
        try {
            const response = await fetchAPI(`${API_BASE}/api/projects/${deleteModal.project.id}`, {
                method: "DELETE",
            });

            if (response.ok) {
                showToast("Project deleted successfully", "success");
                await load();
                closeDeleteModal();
            } else {
                const errorData = await response.json().catch(() => ({detail: "Failed to delete project"}));
                showToast(errorData.detail || "Failed to delete project", "error");
            }
        } catch (error) {
            console.error("Failed to delete project:", error);
            showToast("Failed to delete project. Please try again.", "error");
        } finally {
            setIsDeleting(false);
        }
    }

    async function updateProject(projectId: string, newName: string) {
        try {
            const response = await fetchAPI(`${API_BASE}/api/projects/${projectId}`, {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({name: newName}),
            });
            if (response.ok) {
                showToast("Project updated successfully", "success");
                await load();
                setEditingProject(null);
            } else {
                const errorData = await response.json().catch(() => ({detail: "Failed to update project"}));
                showToast(errorData.detail || "Failed to update project", "error");
            }
        } catch (error) {
            console.error("Failed to update project:", error);
            showToast("Failed to update project. Please try again.", "error");
        }
    }

    // File handling
    const handleFiles = async (files: FileList) => {
        if (selectedAssistant === "cursor") return;
        setIsUploading(true);
        try {
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                if (!file.type.startsWith("image/")) continue;
                const imageUrl = URL.createObjectURL(file);
                setUploadedImages((prev) => [
                    ...prev,
                    {
                        id: crypto.randomUUID(),
                        name: file.name,
                        url: imageUrl,
                        path: "",
                        file,
                    },
                ]);
            }
        } catch (error) {
            console.error("Image processing failed:", error);
            showToast("Failed to process image. Please try again.", "error");
        } finally {
            setIsUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = "";
        }
    };

    const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files) return;
        await handleFiles(files);
    };

    const handleDragEnter = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (selectedAssistant !== "cursor") setIsDragOver(true);
    };
    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setIsDragOver(false);
    };
    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (selectedAssistant !== "cursor") e.dataTransfer.dropEffect = "copy";
        else e.dataTransfer.dropEffect = "none";
    };
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragOver(false);
        if (selectedAssistant === "cursor") return;
        const files = e.dataTransfer.files;
        if (files.length > 0) handleFiles(files);
    };
    const removeImage = (id: string) => {
        setUploadedImages((prev) => {
            const imageToRemove = prev.find((img) => img.id === id);
            if (imageToRemove) URL.revokeObjectURL(imageToRemove.url);
            return prev.filter((img) => img.id !== id);
        });
    };

    // Create project and run prompt
    const handleSubmit = async () => {
        if ((!prompt.trim() && uploadedImages.length === 0) || isCreatingProject) return;
        setIsCreatingProject(true);

        const projectId = `project-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

        try {
            const response = await fetchAPI(`${API_BASE}/api/projects`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    project_id: projectId,
                    name: prompt.slice(0, 50) + (prompt.length > 50 ? "..." : ""),
                    initial_prompt: prompt.trim(),
                    preferred_cli: selectedAssistant,
                    selected_model: selectedModel,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => null);
                console.error("Failed to create project:", errorData);
                showToast("Failed to create project", "error");
                setIsCreatingProject(false);
                return;
            }

            const project = await response.json();

            // Upload images then ACT
            let finalPrompt = prompt.trim();
            let imageData: any[] = [];

            if (uploadedImages.length > 0) {
                try {
                    const uploadedPaths: string[] = [];
                    for (let i = 0; i < uploadedImages.length; i++) {
                        const image = uploadedImages[i];
                        if (!image.file) continue;
                        const formData = new FormData();
                        formData.append("file", image.file);

                        const uploadResponse = await fetchAPI(
                            `${API_BASE}/api/assets/${project.id}/upload`,
                            {method: "POST", body: formData}
                        );
                        if (uploadResponse.ok) {
                            const result = await uploadResponse.json();
                            uploadedPaths.push(`Image #${i + 1} path: ${result.absolute_path}`);
                            imageData.push({
                                name: result.filename || image.name,
                                path: result.absolute_path,
                            });
                        }
                    }
                    if (uploadedPaths.length > 0) {
                        finalPrompt = finalPrompt
                            ? `${finalPrompt}\n\n${uploadedPaths.join("\n")}`
                            : uploadedPaths.join("\n");
                    }
                } catch (uploadError) {
                    console.error("Image upload failed:", uploadError);
                    showToast("Images could not be uploaded, but project was created", "error");
                }
            }

            if (finalPrompt.trim()) {
                try {
                    const actResponse = await fetchAPI(`${API_BASE}/api/chat/${project.id}/act`, {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({
                            instruction: prompt.trim(),
                            images: imageData,
                            is_initial_prompt: true,
                            cli_preference: selectedAssistant,
                        }),
                    });
                    if (!actResponse.ok) {
                        console.error("❌ ACT failed:", await actResponse.text());
                    }
                } catch (actError) {
                    console.error("❌ ACT API error:", actError);
                }
            }

            const params = new URLSearchParams();
            if (selectedAssistant) params.set("cli", selectedAssistant);
            if (selectedModel) params.set("model", selectedModel);
            router.push(`/${project.id}/chat${params.toString() ? "?" + params.toString() : ""}`);
        } catch (error) {
            console.error("Failed to create project:", error);
            showToast("Failed to create project", "error");
            setIsCreatingProject(false);
        }
    };

    // Load projects + paste image support
    useEffect(() => {
        load();

        const handlePaste = (e: ClipboardEvent) => {
            if (selectedAssistant === "cursor") return;
            const items = e.clipboardData?.items;
            if (!items) return;
            const imageFiles: File[] = [];
            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                if (item.type.startsWith("image/")) {
                    const file = item.getAsFile();
                    if (file) imageFiles.push(file);
                }
            }
            if (imageFiles.length > 0) {
                e.preventDefault();
                // Build FileList-like
                const fileList = {
                    length: imageFiles.length,
                    item: (index: number) => imageFiles[index],
                    [Symbol.iterator]: function* () {
                        for (let i = 0; i < imageFiles.length; i++) yield imageFiles[i];
                    },
                } as FileList;
                Object.defineProperty(fileList, "length", {value: imageFiles.length});
                imageFiles.forEach((file, index) => {
                    Object.defineProperty(fileList, index, {value: file});
                });
                handleFiles(fileList);
            }
        };

        document.addEventListener("paste", handlePaste);
        return () => document.removeEventListener("paste", handlePaste);
    }, [selectedAssistant]);

    // Typing animation for placeholder
    const prefix = "Ask Vrabby to create a ";
    const endings = [
        "landing page for my startup",
        "dashboard to manage my team",
        "blog about productivity",
        "web app that tracks expenses",
        "prototype for my new idea",
        "tool that automates reports",
    ];

    const [endingIndex, setEndingIndex] = useState(0);
    const [subIndex, setSubIndex] = useState(0);
    const [deleting, setDeleting] = useState(false);
    const [cursorVisible, setCursorVisible] = useState(true);

    useEffect(() => {
        const current = endings[endingIndex];
        const typingSpeed = deleting ? 15 : 30;
        const timeout = setTimeout(() => {
            if (!deleting && subIndex < current.length) {
                setSubIndex(subIndex + 1);
            } else if (deleting && subIndex > 0) {
                setSubIndex(subIndex - 1);
            } else if (!deleting && subIndex === current.length) {
                setTimeout(() => setDeleting(true), 1800);
            } else if (deleting && subIndex === 0) {
                setDeleting(false);
                setEndingIndex((prev) => (prev + 1) % endings.length);
            }
        }, typingSpeed);
        return () => clearTimeout(timeout);
    }, [subIndex, deleting, endingIndex]);

    useEffect(() => {
        const blink = setInterval(() => setCursorVisible((v) => !v), 500);
        return () => clearInterval(blink);
    }, []);

    // Selections
    const handleAssistantChange = (assistant: string) => {
        if (!cliStatus[assistant]?.installed) return;
        setUsingGlobalDefaults(false);
        setIsInitialLoad(false);
        setSelectedAssistant(assistant);
        if (assistant === "claude") setSelectedModel("claude-sonnet-4.5");
        else if (assistant === "cursor") setSelectedModel("gpt-5");
        else if (assistant === "codex") setSelectedModel("gpt-5");
        else if (assistant === "qwen") setSelectedModel("qwen3-coder-plus");
        else if (assistant === "gemini") setSelectedModel("gemini-2.5-pro");
        setShowAssistantDropdown(false);
    };
    const handleModelChange = (modelId: string) => {
        setUsingGlobalDefaults(false);
        setIsInitialLoad(false);
        setSelectedModel(modelId);
        setShowModelDropdown(false);
    };

    const assistantOptions = [
        {id: "claude", name: "Claude Code", icon: "/claude.png"},
        {id: "codex", name: "Codex CLI", icon: "/oai.png"},
        {id: "cursor", name: "Cursor Agent", icon: "/cursor.png"},
        {id: "gemini", name: "Gemini CLI", icon: "/gemini.png"},
        {id: "qwen", name: "Qwen Coder", icon: "/qwen.png"},
    ];

    // ---- RENDER ----
    return (
        <div className="relative min-h-screen bg-white dark:bg-black">
            {/* Background gradient (kept as-is) */}
            <div className="absolute inset-0">
                <div className="absolute inset-0 bg-white dark:bg-black"/>
                {/* Dark mode glow */}
                <div
                    className="absolute inset-0 hidden dark:block transition-all duration-1000 ease-in-out"
                    style={{
                        background: `radial-gradient(circle at 50% 100%,
              ${assistantBrandColors[selectedAssistant]}66 0%,
              ${assistantBrandColors[selectedAssistant]}4D 25%,
              ${assistantBrandColors[selectedAssistant]}33 50%,
              transparent 70%)`,
                    }}
                />
                {/* Light mode subtle glow */}
                <div
                    className="absolute inset-0 block dark:hidden transition-all duration-1000 ease-in-out"
                    style={{
                        background: `radial-gradient(circle at 50% 100%,
              ${assistantBrandColors[selectedAssistant]}40 0%,
              ${assistantBrandColors[selectedAssistant]}26 25%,
              transparent 50%)`,
                    }}
                />
            </div>

            {/* CONTENT WRAPPER */}
            <div className="relative z-10 flex flex-col min-h-screen">
                {/* ====== HEADER ====== */}
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
                                        <a href="https://discord.gg/APukX5dU3D"
                                           className="hover:text-black dark:hover:text-white transition font-medium">
                                            Community
                                        </a>
                                    </li>
                                    <li>
                                        <a href="#blog"
                                           className="hover:text-black dark:hover:text-white transition font-medium">
                                            Blog
                                        </a>
                                    </li>
                                    <li>
                                        <a href="#faq"
                                           className="hover:text-black dark:hover:text-white transition font-medium">
                                            FAQ
                                        </a>
                                    </li>
                                    <li>
                                        <a href="#pricing"
                                           className="hover:text-black dark:hover:text-white transition font-medium">
                                            Pricing
                                        </a>
                                    </li>
                                </ul>
                            </nav>

                            {/* Right: Auth */}
                            <AuthMenu />

                        </div>
                    </div>
                </header>


                {/* ====== HERO + INPUT ====== */}
                <main className="flex-1">
                    <div className="mx-auto max-w-4xl px-4 pt-52 md:pt-60 pb-8">


                        <div className="text-center mb-10">
                            <div className="flex justify-center mb-6">
                                <img
                                    src="/Vrabby_Icon.svg"
                                    alt="Vrabby Logo"
                                    className="select-none transition-opacity duration-1000 ease-in-out"
                                    style={{width: "130px", objectFit: "contain"}}
                                />
                            </div>

                            <p className="text-xl text-gray-700 dark:text-white/80 font-light tracking-tight">
                                Build powerful apps and websites just by talking to AI.
                            </p>
                        </div>

                        {/* Uploaded image thumbnails */}
                        {uploadedImages.length > 0 && (
                            <div className="mb-4 flex flex-wrap gap-2">
                                {uploadedImages.map((image, index) => (
                                    <div key={image.id} className="relative group">
                                        <img
                                            src={image.url}
                                            alt={image.name}
                                            className="w-20 h-20 object-cover rounded-lg border border-gray-200 dark:border-gray-600"
                                        />
                                        <div
                                            className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-xs px-1 py-0.5 rounded-b-lg">
                                            Image #{index + 1}
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => removeImage(image.id)}
                                            className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
                                        >
                                            ×
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Textarea card */}
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                handleSubmit();
                            }}
                            onDragEnter={handleDragEnter}
                            onDragLeave={handleDragLeave}
                            onDragOver={handleDragOver}
                            onDrop={handleDrop}
                            className={`group flex flex-col gap-4 p-4 w-full rounded-[28px] border backdrop-blur-xl text-base shadow-xl transition-all duration-150 ease-in-out relative overflow-visible ${
                                isDragOver
                                    ? "border-[#DE7356] bg-[#DE7356]/10 dark:bg-[#DE7356]/20"
                                    : "border-gray-200 dark:border-white/10 bg-white dark:bg-black/20"
                            }`}
                        >
                            <div className="relative flex flex-1 items-center">
                                <style jsx>{`
                                    .placeholder-typing::after {
                                        content: "|";
                                        opacity: ${cursorVisible ? 1 : 0};
                                        transition: opacity 0.2s ease-in-out;
                                        color: ${assistantBrandColors[selectedAssistant]};
                                    }
                                `}</style>

                                <textarea
                                    value={prompt}
                                    onChange={(e) => setPrompt(e.target.value)}
                                    placeholder={`${prefix}${endings[endingIndex].substring(0, subIndex)}`}
                                    disabled={isCreatingProject}
                                    className="flex w-full rounded-md px-2 py-2 placeholder:text-gray-400 dark:placeholder:text-white/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50 resize-none text-[16px] leading-snug md:text-base focus-visible:ring-0 focus-visible:ring-offset-0 bg-transparent focus:bg-transparent flex-1 text-gray-900 dark:text-white overflow-y-auto placeholder-typing"
                                    style={{height: "120px"}}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                            if (e.metaKey || e.ctrlKey) {
                                                e.preventDefault();
                                                handleSubmit();
                                            } else if (!e.shiftKey) {
                                                e.preventDefault();
                                                handleSubmit();
                                            }
                                        }
                                    }}
                                />
                            </div>

                            {/* Drag overlay */}
                            {isDragOver && selectedAssistant !== "cursor" && (
                                <div
                                    className="absolute inset-0 bg-[#DE7356]/10 dark:bg-[#DE7356]/20 rounded-[28px] flex items-center justify-center z-10 border-2 border-dashed border-[#DE7356]">
                                    <div className="text-center">
                                        <div className="text-3xl mb-3">📸</div>
                                        <div className="text-lg font-semibold text-[#DE7356] mb-2">Drop images here
                                        </div>
                                        <div className="text-sm text-[#DE7356]">Supports: JPG, PNG, GIF, WEBP</div>
                                    </div>
                                </div>
                            )}

                            {/* Controls row: upload + assistant + model + send */}
                            <div className="flex gap-1 flex-wrap items-center">
                                {/* Upload */}
                                <div className="flex items-center">
                                    {selectedAssistant === "cursor" || selectedAssistant === "qwen" ? (
                                        <div
                                            className="flex items-center justify-center w-8 h-8 text-gray-300 dark:text-gray-600 cursor-not-allowed opacity-50 rounded-full"
                                            title={
                                                selectedAssistant === "qwen"
                                                    ? "Qwen Coder doesn't support image input"
                                                    : "Cursor CLI doesn't support image input"
                                            }
                                        >
                                            <ImageIcon className="h-4 w-4"/>
                                        </div>
                                    ) : (
                                        <label
                                            className="flex items-center justify-center w-8 h-8 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors cursor-pointer"
                                            title="Upload images"
                                        >
                                            <ImageIcon className="h-4 w-4"/>
                                            <input
                                                ref={fileInputRef}
                                                type="file"
                                                accept="image/*"
                                                multiple
                                                onChange={handleImageUpload}
                                                disabled={isUploading || isCreatingProject}
                                                className="hidden"
                                            />
                                        </label>
                                    )}
                                </div>

                                {/* Assistant selector */}
                                <div className="relative z-[200]" ref={assistantDropdownRef}>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setShowAssistantDropdown(!showAssistantDropdown);
                                            setShowModelDropdown(false);
                                        }}
                                        className="justify-center whitespace-nowrap text-sm font-medium transition-colors duration-100 ease-in-out focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 border border-gray-200/50 dark:border-white/5 bg-transparent shadow-sm hover:bg-gray-50 dark:hover:bg-white/5 hover:border-gray-300/50 dark:hover:border-white/10 px-3 py-2 flex h-8 items-center gap-1 rounded-full text-gray-700 dark:text-white/80 hover:text-gray-900 dark:hover:text-white focus-visible:ring-0"
                                    >
                                        <div className="w-4 h-4 rounded overflow-hidden">
                                            <img
                                                src={
                                                    selectedAssistant === "claude"
                                                        ? "/claude.png"
                                                        : selectedAssistant === "cursor"
                                                            ? "/cursor.png"
                                                            : selectedAssistant === "qwen"
                                                                ? "/qwen.png"
                                                                : selectedAssistant === "gemini"
                                                                    ? "/gemini.png"
                                                                    : "/oai.png"
                                                }
                                                alt="cli"
                                                className="w-full h-full object-contain"
                                            />
                                        </div>
                                        <span className="hidden md:flex text-sm font-medium">
                      {selectedAssistant === "claude"
                          ? "Claude Code"
                          : selectedAssistant === "cursor"
                              ? "Cursor Agent"
                              : selectedAssistant === "qwen"
                                  ? "Qwen Coder"
                                  : selectedAssistant === "gemini"
                                      ? "Gemini CLI"
                                      : "Codex CLI"}
                    </span>
                                        <svg
                                            xmlns="http://www.w3.org/2000/svg"
                                            width="12"
                                            height="12"
                                            viewBox="0 -960 960 960"
                                            className="shrink-0 h-3 w-3 rotate-90"
                                            fill="currentColor"
                                        >
                                            <path
                                                d="M530-481 353-658q-9-9-8.5-21t9.5-21 21.5-9 21.5 9l198 198q5 5 7 10t2 11-2 11-7 10L396-261q-9 9-21 8.5t-21-9.5-9-21.5 9-21.5z"/>
                                        </svg>
                                    </button>

                                    {showAssistantDropdown && (
                                        <div
                                            className="absolute top-full mt-1 left-0 z-[300] min-w-full whitespace-nowrap rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 backdrop-blur-xl shadow-lg">
                                            {assistantOptions.map((option) => (
                                                <button
                                                    key={option.id}
                                                    onClick={() => handleAssistantChange(option.id)}
                                                    disabled={!cliStatus[option.id]?.installed}
                                                    className={`w-full flex items-center gap-2 px-3 py-2 text-left first:rounded-t-2xl last:rounded-b-2xl transition-colors ${
                                                        !cliStatus[option.id]?.installed
                                                            ? "opacity-50 cursor-not-allowed text-gray-400 dark:text-gray-500"
                                                            : selectedAssistant === option.id
                                                                ? "bg-gray-100 dark:bg-white/10 text-black dark:text-white font-semibold"
                                                                : "text-gray-800 dark:text-gray-200 hover:text-black dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/10"
                                                    }`}
                                                >
                                                    <div className="w-4 h-4 rounded overflow-hidden">
                                                        <img src={option.icon} alt={option.name}
                                                             className="w-full h-full object-contain"/>
                                                    </div>
                                                    <span className="text-sm font-medium">{option.name}</span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Model selector */}
                                <div className="relative z-[200]" ref={modelDropdownRef}>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setShowModelDropdown(!showModelDropdown);
                                            setShowAssistantDropdown(false);
                                        }}
                                        className="justify-center whitespace-nowrap text-sm font-medium transition-colors duration-100 ease-in-out focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 border border-gray-200/50 dark:border-white/5 bg-transparent shadow-sm hover:bg-gray-50 dark:hover:bg-white/5 hover:border-gray-300/50 dark:hover:border-white/10 px-3 py-2 flex h-8 items-center gap-1 rounded-full text-gray-700 dark:text-white/80 hover:text-gray-900 dark:hover:text-white focus-visible:ring-0 min-w-[140px]"
                                    >
                    <span className="text-sm font-medium whitespace-nowrap">
                      {(() => {
                          const found = availableModels.find((m) => m.id === selectedModel);
                          if (!found) {
                              if (selectedAssistant === "cursor" && selectedModel === "gpt-5") return "GPT-5";
                              if (selectedAssistant === "claude" && selectedModel === "claude-sonnet-4.5")
                                  return "Claude Sonnet 4.5";
                              if (selectedAssistant === "codex" && selectedModel === "gpt-5") return "GPT-5";
                              if (selectedAssistant === "qwen" && selectedModel === "qwen3-coder-plus")
                                  return "Qwen3 Coder Plus";
                              if (selectedAssistant === "gemini" && selectedModel === "gemini-2.5-pro")
                                  return "Gemini 2.5 Pro";
                              if (selectedAssistant === "gemini" && selectedModel === "gemini-2.5-flash")
                                  return "Gemini 2.5 Flash";
                          }
                          return found?.name || "Select Model";
                      })()}
                    </span>
                                        <svg
                                            xmlns="http://www.w3.org/2000/svg"
                                            width="12"
                                            height="12"
                                            viewBox="0 -960 960 960"
                                            className="shrink-0 h-3 w-3 rotate-90 ml-auto"
                                            fill="currentColor"
                                        >
                                            <path
                                                d="M530-481 353-658q-9-9-8.5-21t9.5-21 21.5-9 21.5 9l198 198q5 5 7 10t2 11-2 11-7 10L396-261q-9 9-21 8.5t-21-9.5-9-21.5 9-21.5z"/>
                                        </svg>
                                    </button>

                                    {showModelDropdown && (
                                        <div
                                            className="absolute top-full mt-1 left-0 z-[300] min-w-full max-h-[300px] overflow-y-auto rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 backdrop-blur-xl shadow-lg">
                                            {availableModels.map((model) => (
                                                <button
                                                    key={model.id}
                                                    onClick={() => handleModelChange(model.id)}
                                                    className={`w-full px-3 py-2 text-left first:rounded-t-2xl last:rounded-b-2xl transition-colors ${
                                                        selectedModel === model.id
                                                            ? "bg-gray-100 dark:bg-white/10 text-black dark:text-white font-semibold"
                                                            : "text-gray-800 dark:text-gray-200 hover:text-black dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/10"
                                                    }`}
                                                >
                                                    <span className="text-sm font-medium">{model.name}</span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Send button */}
                                <div className="ml-auto flex items-center">
                                    <button
                                        type="submit"
                                        disabled={(!prompt.trim() && uploadedImages.length === 0) || isCreatingProject}
                                        className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-900 dark:bg-white text-white dark:text-gray-900 transition-opacity duration-150 ease-out disabled:cursor-not-allowed disabled:opacity-50 hover:scale-110"
                                        title="Send (Enter)"
                                    >
                                        {isCreatingProject ? (
                                            <svg
                                                className="animate-spin h-4 w-4"
                                                xmlns="http://www.w3.org/2000/svg"
                                                fill="none"
                                                viewBox="0 0 24 24"
                                            >
                                                <circle className="opacity-25" cx="12" cy="12" r="10"
                                                        stroke="currentColor" strokeWidth="4"></circle>
                                                <path
                                                    className="opacity-75"
                                                    fill="currentColor"
                                                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                                ></path>
                                            </svg>
                                        ) : (
                                            <svg
                                                xmlns="http://www.w3.org/2000/svg"
                                                width="20"
                                                height="20"
                                                viewBox="0 -960 960 960"
                                                className="shrink-0"
                                                fill="currentColor"
                                            >
                                                <path
                                                    d="M442.39-616.87 309.78-487.26q-11.82 11.83-27.78 11.33t-27.78-12.33q-11.83-11.83-11.83-27.78 0-15.96 11.83-27.79l198.43-199q11.83-11.82 28.35-11.82t28.35 11.82l198.43 199q11.83 11.83 11.83 27.79 0 15.95-11.83 27.78-11.82 11.83-27.78 11.83t-27.78-11.83L521.61-618.87v348.83q0 16.95-11.33 28.28-11.32 11.33-28.28 11.33t-28.28-11.33q-11.33-11.33-11.33-28.28z"/>
                                            </svg>
                                        )}
                                    </button>
                                </div>
                            </div>
                        </form>

                        {/* ===== TRUSTED BY SECTION (Bolt-style) ===== */}
                        <section className="relative z-10 mt-32 px-4 select-none">
                            <div className="flex flex-col items-center text-center gap-3">
                                {/* Header */}
                                <p className="font-semibold text-[11px] tracking-widest uppercase text-gray-500 dark:text-gray-400 mb-2">
                                    Trusted by companies that build the future
                                </p>

                                {/* Centered static logos */}
                                <div className="flex flex-wrap justify-center items-center gap-x-12 gap-y-6">
                                    {logos.map((logo, i) => (
                                        <div
                                            key={i}
                                            className="flex items-center justify-center flex-shrink-0"
                                        >
                                            <Image
                                                src={`/trusted/${logo}`}
                                                alt={logo.replace(".webp", "")}
                                                width={120}
                                                height={48}
                                                draggable={false}
                                                className="h-8 w-auto opacity-50 hover:opacity-100 transition duration-500 object-contain brightness-0 invert"
                                                priority={i < 3}
                                            />
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </section>


                    </div>

                    {/* ====== PROJECTS GRID (Lovable-style) ====== */}
                    <section className="mx-auto max-w-6xl px-4 pb-16">
                        <div
                            className="rounded-[28px] border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/40 backdrop-blur-2xl shadow-xl p-4 md:p-6">
                            <div className="flex items-center justify-between mb-4 md:mb-6">
                                <h2 className="text-lg md:text-xl font-semibold text-gray-900 dark:text-white">
                                    From your projects
                                </h2>
                            </div>

                            {projects.length === 0 ? (
                                <div className="py-10 text-center text-gray-500 dark:text-gray-400">
                                    No projects yet — start by typing a prompt above.
                                </div>
                            ) : (
                                <div
                                    className="grid gap-3 sm:gap-4 md:gap-5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                                    {projects.map((project) => {
                                        const thumb = project.preview_url?.trim() || "";
                                        const cliName =
                                            project.preferred_cli === "claude"
                                                ? "Claude"
                                                : project.preferred_cli === "cursor"
                                                    ? "Cursor"
                                                    : project.preferred_cli === "qwen"
                                                        ? "Qwen"
                                                        : project.preferred_cli === "gemini"
                                                            ? "Gemini"
                                                            : project.preferred_cli === "codex"
                                                                ? "Codex"
                                                                : project.preferred_cli || "Unknown";

                                        return (
                                            <div
                                                key={project.id}
                                                className="group rounded-2xl overflow-hidden border border-gray-200 dark:border-white/10 bg-white/60 dark:bg-white/[0.06] hover:bg-white/80 dark:hover:bg-white/[0.08] transition shadow"
                                            >
                                                {/* Thumbnail */}
                                                <button
                                                    onClick={() => {
                                                        const params = new URLSearchParams();
                                                        if (selectedAssistant) params.set("cli", selectedAssistant);
                                                        if (selectedModel) params.set("model", selectedModel);
                                                        router.push(
                                                            `/${project.id}/chat${params.toString() ? "?" + params.toString() : ""}`
                                                        );
                                                    }}
                                                    className="block w-full aspect-[16/10] overflow-hidden bg-gradient-to-br from-gray-100 to-gray-200 dark:from-white/10 dark:to-white/5"
                                                    title={project.name}
                                                >
                                                    {thumb ? (
                                                        // Real preview
                                                        // eslint-disable-next-line @next/next/no-img-element
                                                        <img
                                                            src={thumb}
                                                            alt={project.name}
                                                            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                                                        />
                                                    ) : (
                                                        // Placeholder thumbnail
                                                        <div
                                                            className="w-full h-full flex items-center justify-center"
                                                            style={{
                                                                background:
                                                                    "radial-gradient(120% 120% at 0% 0%, rgba(255,255,255,0.35) 0%, rgba(255,255,255,0.08) 40%, transparent 70%)",
                                                            }}
                                                        >
                                                            <div
                                                                className="rounded-xl px-3 py-2 text-sm font-semibold tracking-wide bg-black/70 text-white">
                                                                {getInitials(project.name)}
                                                            </div>
                                                        </div>
                                                    )}
                                                </button>

                                                {/* Meta row */}
                                                <div className="px-3.5 py-3">
                                                    <div className="flex items-center gap-2">
                                                        <div className="min-w-0 flex-1">
                                                            <div
                                                                className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                                                {project.name}
                                                            </div>
                                                            <div className="text-xs text-gray-500 dark:text-gray-400">
                                                                {cliName}
                                                                <span className="mx-1.5">•</span>
                                                                {formatTime(project.last_message_at || project.created_at)}
                                                            </div>
                                                        </div>

                                                        {/* Card actions */}
                                                        <div
                                                            className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                            <button
                                                                onClick={() => setEditingProject(project)}
                                                                className="p-1.5 rounded-md text-gray-500 hover:text-orange-500 hover:bg-gray-100 dark:hover:bg-white/10 transition"
                                                                title="Rename"
                                                            >
                                                                <svg className="w-4 h-4" viewBox="0 0 24 24"
                                                                     fill="none">
                                                                    <path
                                                                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5"
                                                                        stroke="currentColor"
                                                                        strokeWidth="2"
                                                                        strokeLinecap="round"
                                                                        strokeLinejoin="round"
                                                                    />
                                                                    <path
                                                                        d="M15.5 3.5a2.121 2.121 0 013 3L12 13l-4 1 1-4 6.5-6.5z"
                                                                        stroke="currentColor"
                                                                        strokeWidth="2"
                                                                        strokeLinecap="round"
                                                                        strokeLinejoin="round"
                                                                    />
                                                                </svg>
                                                            </button>
                                                            <button
                                                                onClick={() => openDeleteModal(project)}
                                                                className="p-1.5 rounded-md text-gray-500 hover:text-red-500 hover:bg-gray-100 dark:hover:bg-white/10 transition"
                                                                title="Delete"
                                                            >
                                                                <svg className="w-4 h-4" viewBox="0 0 24 24"
                                                                     fill="none">
                                                                    <path
                                                                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M4 7h16"
                                                                        stroke="currentColor"
                                                                        strokeWidth="2"
                                                                        strokeLinecap="round"
                                                                        strokeLinejoin="round"
                                                                    />
                                                                </svg>
                                                            </button>
                                                        </div>
                                                    </div>

                                                    {/* Inline rename form (if needed) */}
                                                    {editingProject?.id === project.id && (
                                                        <form
                                                            onSubmit={(e) => {
                                                                e.preventDefault();
                                                                const formData = new FormData(e.target as HTMLFormElement);
                                                                const newName = formData.get("name") as string;
                                                                if (newName.trim()) updateProject(project.id, newName.trim());
                                                            }}
                                                            className="mt-2 flex items-center gap-2"
                                                        >
                                                            <input
                                                                name="name"
                                                                defaultValue={project.name}
                                                                className="w-full px-2 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
                                                                autoFocus
                                                                onBlur={() => setEditingProject(null)}
                                                            />
                                                            <button
                                                                type="submit"
                                                                className="px-2 py-1 text-xs bg-orange-500 text-white rounded hover:bg-orange-600 transition-colors"
                                                            >
                                                                Save
                                                            </button>
                                                            <button
                                                                type="button"
                                                                onClick={() => setEditingProject(null)}
                                                                className="px-2 py-1 text-xs bg-gray-500 text-white rounded hover:bg-gray-600 transition-colors"
                                                            >
                                                                Cancel
                                                            </button>
                                                        </form>
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </section>
                </main>

                {/* ====== FOOTER (Minimal Premium Style) ====== */}
                <footer className="mt-auto pb-10">
                    <div className="mx-auto max-w-6xl px-4">
                        <div
                            className="rounded-[28px] border border-gray-200 dark:border-white/10 bg-white/60 dark:bg-black/40 backdrop-blur-2xl shadow-lg px-8 py-10 flex flex-col md:flex-row items-center justify-between gap-6">

                            {/* Left: logo + subtle tagline */}
                            <div className="flex flex-col items-center md:items-start text-center md:text-left">
                                <img
                                    src="/Vrabby_Icon.svg"
                                    alt="Vrabby"
                                    className="h-10 w-auto mb-3 opacity-90 drop-shadow-[0_0_6px_rgba(66,133,244,0.35)] dark:drop-shadow-[0_0_8px_rgba(66,133,244,0.5)] select-none"
                                />
                                <p className="text-sm text-gray-600 dark:text-gray-400 max-w-sm leading-snug">
                                    The creative engine behind the world’s most ambitious teams.
                                </p>
                            </div>

                            {/* Right: quick links + copyright */}
                            <div
                                className="flex flex-col items-center md:items-end gap-3 text-xs text-gray-500 dark:text-gray-400">
                                <div className="flex gap-4 text-sm">
                                    <a href="#pricing"
                                       className="hover:text-gray-800 dark:hover:text-white transition-colors">
                                        Pricing
                                    </a>
                                    <a href="https://discord.gg/APukX5dU3D"
                                       className="hover:text-gray-800 dark:hover:text-white transition-colors">
                                        Community
                                    </a>
                                    <a href="#contact"
                                       className="hover:text-gray-800 dark:hover:text-white transition-colors">
                                        Contact
                                    </a>
                                </div>
                                <div className="opacity-70">
                                    © {new Date().getFullYear()} <span
                                    className="font-medium text-gray-700 dark:text-gray-200">Vrabby</span>. All rights
                                    reserved.
                                </div>
                            </div>
                        </div>
                    </div>
                </footer>


                {/* ===== Modals & Toasts (kept) ===== */}
                <GlobalSettings isOpen={showGlobalSettings} onClose={() => setShowGlobalSettings(false)}/>

                {deleteModal.isOpen && deleteModal.project && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
                        <MotionDiv
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.9 }}
                            className="w-full max-w-sm rounded-2xl border border-white/10 bg-neutral-900 text-white shadow-2xl p-5 relative"
                        >
                            {/* Close button (X) */}
                            <button
                                onClick={closeDeleteModal}
                                className="absolute top-3 right-3 text-gray-400 hover:text-white transition"
                                title="Close"
                            >
                                <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    className="w-5 h-5"
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth="2"
                                        d="M6 18L18 6M6 6l12 12"
                                    />
                                </svg>
                            </button>

                            {/* Title */}
                            <h3 className="text-lg font-semibold mb-1">
                                Delete <span className="text-white/90">{deleteModal.project.name}</span>?
                            </h3>
                            <p className="text-sm text-gray-400 mb-4">
                                This action cannot be undone.{" "}
                                <span className="text-red-400 font-medium">
          This will permanently delete your project.
        </span>{" "}
                                Including:
                            </p>

                            {/* List of what’s deleted */}
                            <ul className="list-disc list-inside text-sm text-gray-400 mb-6 space-y-1">
                                <li>Any deployments made with Vrabby</li>
                                <li>All preview links</li>
                            </ul>

                            {/* Buttons */}
                            <div className="flex justify-end gap-3">
                                <button
                                    onClick={closeDeleteModal}
                                    disabled={isDeleting}
                                    className="px-4 py-2 text-sm rounded-lg bg-neutral-800 text-gray-200 hover:bg-neutral-700 transition disabled:opacity-50"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={deleteProject}
                                    disabled={isDeleting}
                                    className="px-4 py-2 text-sm font-medium rounded-lg bg-red-600 hover:bg-red-700 text-white transition flex items-center gap-2 disabled:opacity-50"
                                >
                                    {isDeleting ? (
                                        <>
                                            <svg
                                                className="animate-spin h-4 w-4"
                                                xmlns="http://www.w3.org/2000/svg"
                                                fill="none"
                                                viewBox="0 0 24 24"
                                            >
                                                <circle
                                                    className="opacity-25"
                                                    cx="12"
                                                    cy="12"
                                                    r="10"
                                                    stroke="currentColor"
                                                    strokeWidth="4"
                                                ></circle>
                                                <path
                                                    className="opacity-75"
                                                    fill="currentColor"
                                                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2
                  5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824
                  3 7.938l3-2.647z"
                                                ></path>
                                            </svg>
                                            Deleting...
                                        </>
                                    ) : (
                                        "Continue"
                                    )}
                                </button>
                            </div>
                        </MotionDiv>
                    </div>
                )}


                {toast && (
                    <div className="fixed bottom-4 right-4 z-50">
                        <motion.div initial={{opacity: 0, y: 50, scale: 0.9}} animate={{opacity: 1, y: 0, scale: 1}}
                                    exit={{opacity: 0, y: 50, scale: 0.9}}>
                            <div
                                className={`px-6 py-4 rounded-lg shadow-lg border flex items-center gap-3 max-w-sm backdrop-blur-lg ${
                                    toast.type === "success"
                                        ? "bg-green-500/20 border-green-500/30 text-green-400"
                                        : "bg-red-500/20 border-red-500/30 text-red-400"
                                }`}
                            >
                                {toast.type === "success" ? (
                                    <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                                        <path
                                            fillRule="evenodd"
                                            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                            clipRule="evenodd"
                                        />
                                    </svg>
                                ) : (
                                    <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                                        <path
                                            fillRule="evenodd"
                                            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                                            clipRule="evenodd"
                                        />
                                    </svg>
                                )}
                                <p className="text-sm font-medium">{toast.message}</p>
                            </div>
                        </motion.div>
                    </div>
                )}
            </div>
        </div>
    );
}
