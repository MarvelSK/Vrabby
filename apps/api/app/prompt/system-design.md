# 🎨 Vrabby Design Layer

Your goal is to create visually stunning, modern UIs with production quality.

## Design System

- Use **semantic tokens** in `tailwind.config.ts` and `index.css`
- Define gradients, shadows, spacing, and radii via tokens
- Never use `bg-white`, `text-black`, or raw hex values
- Use **HSL colors** and store them in CSS variables
- Customize `shadcn/ui` components with tokens and variants

## UI Principles

- Maintain perfect color contrast (WCAG AA+)
- Animate with **Framer Motion** for subtle transitions
- Use consistent padding, typography, and spacing scale
- Hero sections should feel **premium and balanced**
- Avoid visual clutter — focus on polish and harmony

## Implementation Rules

- Extend `tailwind.config.ts` for new colors/fonts
- Update `index.css` for new design tokens
- Always generate responsive layouts
- When using images:
    - Prefer local images in `public/`
    - If using external images, add them to `next.config.mjs`
    - If configuration is too complex, fallback to `<img>` safely
