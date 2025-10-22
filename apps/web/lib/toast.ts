export type ToastType = "info" | "success" | "error";

export function showToast(message: string, type: ToastType = "info") {
    if (typeof window === "undefined") return;
    const existing = document.getElementById("toast-root");
    const root = existing ?? (() => {
        const el = document.createElement("div");
        el.id = "toast-root";
        el.style.position = "fixed";
        el.style.top = "12px";
        el.style.right = "12px";
        el.style.zIndex = "9999";
        el.style.display = "flex";
        el.style.flexDirection = "column";
        el.style.gap = "8px";
        document.body.appendChild(el);
        return el;
    })();

    const item = document.createElement("div");
    item.textContent = message;
    item.style.padding = "10px 12px";
    item.style.borderRadius = "8px";
    item.style.fontSize = "12px";
    item.style.color = type === "error" ? "#fff" : "#111827";
    item.style.background = type === "success" ? "#10B981" : type === "error" ? "#EF4444" : "rgba(0,0,0,0.08)";
    item.style.boxShadow = "0 4px 12px rgba(0,0,0,0.12)";
    item.style.transition = "opacity 200ms";
    root.appendChild(item);

    setTimeout(() => {
        item.style.opacity = "0";
        setTimeout(() => {
            root.removeChild(item);
            if (!root.hasChildNodes()) {
                root.remove();
            }
        }, 200);
    }, 3000);
}
