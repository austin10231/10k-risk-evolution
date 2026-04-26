# AGENTS.md

## Purpose
This file defines how the agent (Codex) should work on this project, especially for frontend UI improvements.

---

## General Rules

- Do NOT change business logic unless explicitly requested.
- Do NOT modify backend, API, or data flow unless clearly instructed.
- Only focus on the requested scope.
- Prefer minimal, clean, and maintainable changes.
- Avoid unnecessary rewrites of unrelated files.

---

## Workflow (MANDATORY)

When working on frontend UI:

1. **Inspect first**
   - Understand existing structure (components, layout, CSS, Tailwind, etc.)
   - Identify current design issues

2. **If design direction is unclear**
   - Propose 2–3 UI design directions (e.g., modern SaaS, minimal, creative)
   - Briefly describe each (layout, typography, spacing, colors)
   - WAIT for confirmation before coding

3. **Plan before coding**
   - Provide a short improvement plan (what will be changed and why)

4. **Then implement**
   - Apply changes step-by-step
   - Do NOT break functionality

5. **After implementation**
   - Review visual consistency
   - Ensure responsive design
   - Summarize what was changed

---

## Frontend Design Principles

The UI should feel **production-ready**, not like a default template.

### Layout
- Clear visual hierarchy (title → section → content)
- Use spacing to separate sections
- Avoid cluttered layouts
- Align elements properly

### Spacing
- Use consistent spacing (prefer 8px system: 8, 16, 24, 32...)
- Add enough padding inside cards and sections
- Avoid elements being too close together

### Typography
- Use clear hierarchy:
  - Large, bold headings
  - Medium section titles
  - Subtle secondary text
- Avoid too many font styles
- Keep text readable

### Components
- Cards should:
  - Have padding
  - Rounded corners
  - Subtle shadows or borders
- Buttons should:
  - Have hover states
  - Look clickable and polished
- Inputs should:
  - Be aligned and consistent
  - Have focus states

### Colors
- Use a consistent color system
- Avoid random or conflicting colors
- Prefer:
  - Neutral background
  - One primary color
  - Subtle accent colors

### Visual Quality
- Avoid default/plain HTML look
- Avoid inconsistent styles
- UI should look like a real product (SaaS-level quality)

---

## Responsiveness

- UI must work on different screen sizes
- Avoid fixed widths when possible
- Ensure layout adapts properly (mobile/tablet/desktop)

---

## Code Quality

- Prefer reusable components
- Keep code clean and readable
- Follow existing project structure
- Do not introduce unnecessary dependencies

---

## What NOT to do

- Do NOT randomly redesign everything without a plan
- Do NOT ignore existing styles/components
- Do NOT break layout responsiveness
- Do NOT introduce inconsistent design patterns
- Do NOT overcomplicate the UI

---

## When the user is unsure about UI

If the user says things like:
- "make it better"
- "optimize UI"
- "not good-looking"

You MUST:
1. Analyze current UI
2. Propose multiple design directions
3. Wait for user to choose
4. Then implement

---

## Goal

The final result should:
- Look modern and polished
- Be clean and easy to use
- Maintain consistency across the app
- Feel like a real production product