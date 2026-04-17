# Design System Specification: High-End Editorial Governance

## 1. Overview & Creative North Star
### The Creative North Star: "The Sovereign Ledger"
This design system rejects the cluttered, line-heavy aesthetic of traditional project management tools. Instead, it adopts the persona of **The Sovereign Ledger**—a digital environment that feels like an authoritative editorial publication mixed with a precision-engineered cockpit.

We move beyond "standard SaaS" by utilizing **intentional asymmetry**, high-contrast typography scales, and **tonal depth** rather than structural borders. The goal is to provide a sense of absolute governance and AI-driven clarity. We are not just managing tasks; we are overseeing an enterprise's intellectual capital. 

The experience must feel:
*   **Architectural:** Using space as a structural element.
*   **Weighted:** Every interaction feels intentional and stable.
*   **Invisible:** The UI gets out of the way of complex data through sophisticated layering.

---

## 2. Colors & Surface Philosophy
The palette is rooted in deep technical blues and slate grays, but its execution is what creates the premium feel.

### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders to section off major layout areas. 
*   Boundaries are defined by **background color shifts**. 
*   A sidebar should reside on `primary-container` (#131B2E), while the main workspace sits on `surface` (#F7F9FB).
*   Content modules within the workspace should use `surface-container-low` (#F2F4F6) to create natural separation without visual "noise."

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers. Use the `surface-container` tiers to define importance:
1.  **Base Layer:** `surface` (#F7F9FB) – The canvas.
2.  **Sectioning:** `surface-container-low` (#F2F4F6) – Used for grouping related data tables or boards.
3.  **Active Elements:** `surface-container-lowest` (#FFFFFF) – Used for cards, modals, or active input fields to make them "pop" against the background.

### The "Glass & Gradient" Rule
To elevate the platform above generic B2B software:
*   **Floating Navigation/Filters:** Use Glassmorphism. Apply `surface-container-lowest` with a 70% opacity and a `24px` backdrop-blur.
*   **Signature Textures:** For primary CTAs and AI-insight banners, use a subtle linear gradient from `primary` (#000000) to `primary-container` (#131B2E) at a 135-degree angle. This adds "soul" and depth to an otherwise flat interface.

---

## 3. Typography: The Editorial Voice
We utilize a dual-font strategy to balance technical readability with high-end authority.

*   **Display & Headlines (Manrope):** Use Manrope for all `display-` and `headline-` levels. It provides a geometric, modern authority. Set `display-lg` with a `-0.02em` letter spacing to mimic high-end print.
*   **Data & Utility (Inter):** Use Inter for all `title-`, `body-`, and `label-` levels. Inter’s tall x-height ensures that data-heavy Kanban boards and tables remain legible even at `body-sm` (#0.75rem).

**Hierarchy Principle:** Use extreme contrast. A `display-md` headline should sit near a `label-md` metadata point. This "Big & Small" approach creates a sophisticated, non-linear layout that guides the eye to what matters most: the governance status.

---

## 4. Elevation & Depth
In this design system, shadows are a last resort. We use **Tonal Layering** to convey hierarchy.

### The Layering Principle
Depth is achieved by "stacking" surface tiers. Place a `surface-container-lowest` card on top of a `surface-container-low` background. This creates a soft, natural lift that feels integrated into the environment.

### Ambient Shadows
When a floating effect is required (e.g., a dropdown or a critical modal):
*   **Blur:** 40px to 60px.
*   **Opacity:** 4% to 8%.
*   **Color:** Use the `on-surface` (#191C1E) color as the shadow base to ensure the shadow feels like a natural obstruction of light, not a gray smudge.

### The "Ghost Border" Fallback
If a border is required for accessibility (e.g., in a high-density table):
*   Use the `outline-variant` (#C6C6CD) token at **15% opacity**. 
*   **Prohibited:** 100% opaque, high-contrast borders.

---

## 5. Components

### Modern Tables & Status Badges
*   **Tables:** Forbid divider lines between rows. Use a vertical spacing of `16px` between rows and a `surface-container-lowest` hover state.
*   **Status Badges:** Use `tertiary-container` (#002109) with `on-tertiary-container` (#009844) text for "Success/Healthy" statuses. The shape must be a "Soft Pill" using `rounded-full`.

### Cards & Modules
*   **Structure:** No borders. Use `surface-container-lowest` and a `rounded-lg` (0.5rem) corner.
*   **Content:** Group information using `body-sm` for labels and `title-sm` for values. Use vertical white space (12px, 16px, 24px) to separate content sections instead of horizontal rules.

### Buttons & Actions
*   **Primary Action:** `primary` (#000000) background with `on-primary` (#FFFFFF) text. Use `rounded-md` (0.375rem).
*   **Secondary/Filter Action:** `surface-container-high` (#E6E8EA) background. This keeps the focus on the primary governance tasks.

### Sidebar Navigation
*   **Fixed Sidebar:** Use `primary-container` (#131B2E). Icons should be `outline-variant` (#C6C6CD) when inactive, and `primary-fixed` (#DAE2FD) when active. This creates a deep, "command center" aesthetic.

### AI Governance Insights (Custom Component)
*   **The "Insight Card":** A specialized card using a subtle gradient border (created with a 1px inner padding on a gradient background). Use `tertiary-fixed` (#6BFF8F) sparingly as a glow effect to indicate AI-driven suggestions.

---

## 6. Do's and Don'ts

### Do
*   **Do** use asymmetrical layouts where the left column is significantly wider or narrower than the right to create an editorial feel.
*   **Do** use `body-sm` in all-caps with `0.05em` tracking for labels to give them a "technical metadata" vibe.
*   **Do** prioritize white space over lines. If the layout feels "loose," add more space, not more borders.

### Don't
*   **Don't** use pure black for text. Use `on-surface` (#191C1E) or `on-surface-variant` (#45464D) for a softer, premium look.
*   **Don't** use traditional "Drop Shadows" on cards. Rely on background color shifts.
*   **Don't** use standard 12-column grids for everything. Allow specific elements (like AI insights) to break the grid and overlap containers slightly.