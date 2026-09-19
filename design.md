## Design Plan

**The idea:** Since this is a filesystem tool, the file tree itself should be part of the UI — not just a chat box. Seeing folders and files appear/change live on screen makes the "AI did something real" feeling much stronger, and it naturally makes the interface feel like a proper dev tool (think Linear, Raycast, VS Code) rather than a generic chatbot template.

### 1. Color Palette

| Role             | Color                                                 | Hex       |
| ---------------- | ----------------------------------------------------- | --------- |
| Background       | Deep ink navy (not pure black — softer, more premium) | `#0F1419` |
| Panel/Surface    | Slightly lighter navy                                 | `#161B22` |
| Border/Divider   | Subtle line                                           | `#262D38` |
| Text (primary)   | Warm off-white                                        | `#EDEAE3` |
| Text (secondary) | Muted grey-blue                                       | `#8B93A1` |
| Accent           | Brushed brass/gold — used sparingly                   | `#C9A659` |

Why: pure black + neon accent is the overused "AI-generated" look. A deep navy with a warm brass accent feels more like a crafted, expensive tool (closer to premium fintech or dev-tool apps) than a template.

### 2. Typography

- **Headings/UI labels:** Sora (clean, modern, slightly geometric — good "premium software" feel)
- **File paths, commands, timestamps:** IBM Plex Mono (monospace makes technical content feel intentional, not just styled text)

Only these two fonts. No all-caps labels, no extra "eyebrow" text above sections — keep it clean.

### 3. Layout

```
┌─────────────┬──────────────────────────────┐
│  WORKSPACE  │        Chat with your files    │
│             │                                │
│ 📁 mcp-      │  You: create a folder Projects │
│   workspace │  ✓ Created Projects/           │
│  📁 Projects│                                │
│  📄 notes.  │  You: read notes.txt           │
│     txt     │  [shows file content]          │
│             │                                │
│             │                                │
├─────────────┼──────────────────────────────┤
│             │  [ type a command...      ➤ ] │
└─────────────┴──────────────────────────────┘
```

- **Left panel:** live file tree of the sandboxed folder — updates automatically whenever a file action happens
- **Right panel:** the chat conversation
- **Bottom bar:** input box, styled like a calm command line, not a bouncy chat bubble input

### 4. The One Special Moment (motion)

Keep animation minimal, but use **one** meaningful effect: when a file action completes, the matching row in the file tree briefly glows in the brass accent color, then fades back to normal. This visually connects "what you typed" to "what happened" — which is the whole point of the tool. No other hover animations or fade-ins needed.

### 5. Small details that create the "premium" feel

- Rounded corners: small and consistent (6–8px), not the generic bubbly card look
- No drop shadows except one subtle shadow under the chat panel to lift it slightly off the background
- Delete confirmation appears as a small inline card inside the chat (not a browser popup) — keeps the experience contained and calm
- Empty state (no files yet): a simple line like "This folder is empty — try 'create a file called notes.txt'" instead of a generic "No data" message

---

### Prompt to give Antigravity

> "Build a React chat UI with two panels: a left sidebar showing a live file tree of the `mcp-workspace` sandbox folder, and a right panel with the chat conversation. Use a dark navy background (#0F1419), panel color #161B22, borders #262D38, text color #EDEAE3, and a brass accent color #C9A659 used only for active states and success confirmations. Use the Sora font for UI text and IBM Plex Mono for file paths and timestamps. When a file action completes, briefly highlight the matching row in the file tree sidebar with the accent color, then fade it back to normal. Style the input bar like a calm command line at the bottom of the chat panel. Show delete confirmations as an inline card inside the chat, not a browser alert. Keep corner radius small (6-8px), avoid drop shadows except a subtle one under the chat panel, and avoid decorative gradients."
