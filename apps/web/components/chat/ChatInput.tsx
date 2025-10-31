"use client";

import { useState, useRef, useEffect } from "react";
import { SendHorizontal, MessageSquare, Image, X } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080";

interface UploadedImage {
  id: string;
  filename: string;
  path: string;
  url: string;
}

interface ChatInputProps {
  onSendMessage: (message: string, images?: UploadedImage[]) => void;
  disabled?: boolean;
  placeholder?: string;
  mode?: "act" | "chat";
  onModeChange?: (mode: "act" | "chat") => void;
  projectId?: string;
  preferredCli?: string;
}

export default function ChatInput({
  onSendMessage,
  disabled = false,
  placeholder = "Ask Vrabby...",
  mode = "act",
  onModeChange,
  projectId,
  preferredCli = "claude",
}: ChatInputProps) {
  const [message, setMessage] = useState("");
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "42px";
    const h = ta.scrollHeight;
    ta.style.height = `${Math.min(h, 300)}px`;
    ta.style.overflowY = h > 300 ? "auto" : "hidden";
  }, [message]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if ((message.trim() || uploadedImages.length > 0) && !disabled) {
      onSendMessage(message.trim(), uploadedImages);
      setMessage("");
      setUploadedImages([]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    await handleFiles(files);
  };

  const handleFiles = async (files: FileList) => {
    if (!projectId || preferredCli === "cursor" || preferredCli === "qwen") return;

    setIsUploading(true);
    try {
      for (const file of files) {
        if (!file.type.startsWith("image/")) continue;
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch(`${API_BASE}/api/assets/${projectId}/upload`, { method: "POST", body: fd });
        if (!res.ok) throw new Error("Upload failed");
        const data = await res.json();
        setUploadedImages((p) => [
          ...p,
          {
            id: crypto.randomUUID(),
            filename: data.filename,
            path: data.absolute_path,
            url: URL.createObjectURL(file),
          },
        ]);
      }
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const removeImage = (id: string) =>
    setUploadedImages((p) => p.filter((img) => img.id !== id));

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl px-3 py-3 flex flex-col gap-3 shadow-inner"
      style={{ backgroundColor: "#272725", color: "#eeedf8" }}
    >
      {/* image previews */}
      {uploadedImages.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-1">
          {uploadedImages.map((img) => (
            <div
              key={img.id}
              className="relative w-[52px] h-[52px] rounded-lg overflow-hidden border border-zinc-700"
            >
              <img src={img.url} alt="preview" className="object-cover w-full h-full" />
              <button
                type="button"
                onClick={() => removeImage(img.id)}
                className="absolute -top-1 -right-1 bg-[#272725]/90 text-zinc-300 rounded-full p-[1px] hover:text-red-400"
                title="Remove"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* textarea */}
      <textarea
        ref={textareaRef}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full resize-none bg-transparent border-none focus:ring-0 focus:outline-none placeholder-[#a3a1b0] text-[13px] leading-snug"
        style={{ color: "#eeedf8", minHeight: "42px", maxHeight: "300px", overflowY: "auto" }}
      />

      {/* bottom bar */}
      <div className="flex items-center justify-between mt-1">
        <div className="flex items-center gap-1.5">
          {/* image */}
          {projectId && preferredCli !== "cursor" && preferredCli !== "qwen" && (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading || disabled}
              className="flex items-center gap-1 px-2 py-[3px] rounded-md text-[12.5px] font-medium text-[#d1d0da] bg-[#343432] hover:bg-[#3f3f3d] transition-all"
              style={{ height: "24px" }}
              title="Attach image"
            >
              <Image className="h-3.5 w-3.5" />
              <span>Image</span>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={handleImageUpload}
                className="hidden"
              />
            </button>
          )}

          {/* chat */}
          <button
            type="button"
            onClick={() => onModeChange?.(mode === "chat" ? "act" : "chat")}
            className={`flex items-center gap-1 px-2 py-[3px] rounded-md text-[12.5px] font-medium transition-all ${
              mode === "chat"
                ? "bg-blue-600/20 text-blue-400 border border-blue-500/30 shadow-[0_0_4px_rgba(37,99,235,0.3)]"
                : "text-[#d1d0da] bg-[#343432] hover:bg-[#3f3f3d]"
            }`}
            style={{ height: "24px" }}
            title="Toggle Chat Mode"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            <span>Chat</span>
          </button>
        </div>

        {/* send */}
        <button
          id="chatinput-send-message-button"
          type="submit"
          disabled={
            disabled ||
            (!message.trim() && uploadedImages.length === 0) ||
            isUploading
          }
          className="flex items-center justify-center w-[24px] h-[24px] rounded-md bg-gradient-to-br from-blue-500 to-indigo-500 text-white hover:from-blue-400 hover:to-indigo-400 active:scale-95 transition-all disabled:opacity-40 shadow-sm"
          title="Send message"
        >
          <SendHorizontal className="h-3.5 w-3.5" />
        </button>
      </div>
    </form>
  );
}
