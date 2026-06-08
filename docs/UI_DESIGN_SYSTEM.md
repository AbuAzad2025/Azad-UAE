# UI Design System

## 1. Design Tokens

### Colors

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--ui-bg` | #F8F7F2 | #0B1220 | Page background |
| `--ui-surface` | #FFFFFF | #121B2D | Cards, panels |
| `--ui-surface-2` | #F2F1EC | #0F172A | Alternate surfaces |
| `--ui-text` | #0F172A | #E5E7EB | Primary text |
| `--ui-muted` | #475569 | #A3B1C6 | Secondary text |
| `--ui-border` | #D7D4C8 | rgba(255,255,255,0.12) | Borders |
| `--ui-primary` | #0E5A3A | #22A06B | Primary brand |
| `--ui-primary-2` | #0B3F2A | #137A4F | Primary hover |
| `--ui-accent` | #B11E2B | #E23D4B | Accent/CTA |
| `--ui-success` | #188A4C | #2FD07F | Success states |
| `--ui-danger` | #B11E2B | #E23D4B | Error states |
| `--ui-warning` | #C97C10 | #F0A83A | Warning states |
| `--ui-info` | #1D6FA3 | #58B9F6 | Info states |

### Shadows

| Token | Value |
|-------|-------|
| `--ui-shadow` | 0 10px 24px rgba(15, 23, 42, 0.08) |
| `--ui-shadow-strong` | 0 16px 40px rgba(15, 23, 42, 0.14) |

### Radius

| Token | Value |
|-------|-------|
| `--ui-radius-sm` | 10px |
| `--ui-radius-md` | 14px |
| `--ui-radius-lg` | 18px |

### Typography

| Token | Value |
|-------|-------|
| `--ui-font-family` | 'Tajawal', system-ui, -apple-system, 'Segoe UI', Tahoma, Arial, sans-serif |

## 2. Components

### Stat Card

```html
<div class="stat-card">
  <div class="stat-icon ic-N">
    <i class="fas fa-icon"></i>
  </div>
  <div class="stat-value">1,250</div>
  <div class="stat-label">Label</div>
  <a href="..." class="btn btn-primary mt-2 w-100">Action</a>
</div>
```

- Left accent border (gradient primary→accent)
- Hover: subtle lift + stronger shadow
- Mobile: reduced padding and font size

### Glass Effect Card

```html
<div class="card glass-effect">
  <div class="card-body">...</div>
</div>
```

- Semi-transparent white background
- Backdrop blur
- Subtle border
- Dark mode: inverted opacity

### Hover Card

```html
<a href="..." class="card hover-card">...</a>
```

- Hover: translateY(-4px) + stronger shadow
- Used for quick action cards

### Badges

| Class | Colors |
|-------|--------|
| `.badge-success` | Green gradient |
| `.badge-warning` | Amber gradient |
| `.badge-danger` | Red gradient |
| `.badge-info` | Blue gradient |
| `.badge-primary` | Brand gradient |
| `.badge-secondary` | Gray gradient |

All badges: 8px radius, 700 weight, white text.

## 3. Tables

- Header: faint background, 800 weight
- Hover: subtle row highlight
- Actions: compact button group (36px min-height)
- Responsive wrapper: `.table-responsive`

## 4. Forms

- Min height: 44px
- Radius: 12px
- Focus ring: primary color with 22% opacity
- Select2: matches form controls

## 5. Buttons

- Min height: 44px
- Radius: 12px
- Primary: gradient with shadow on hover
- All touch-friendly

## 6. Sidebar

- Background: gradient (deep navy)
- Active item: white background + teal left border accent
- Hover: semi-transparent white background
- RTL: border radius flipped

## 7. Mobile

- KPI cards: smaller padding/font on < 768px
- Tables: horizontal scroll via `.table-responsive`
- Buttons: no `btn-sm` (all 44px min)
- Content wrapper bottom padding: 48px on mobile

## 8. RTL

- Uses logical properties: `margin-inline-*`, `padding-inline-*`, `border-inline-*`, `inset-inline-*`
- Sidebar nav: `flex-direction: row-reverse` with `gap`
- Active indicator border radius flips for RTL

## 9. Variants

### Palestinian (default)

- Primary: emerald green
- Accent: red
- Gold: #C9A227

### Gulf

- Primary: deep navy #0B2A4A
- Accent: teal #0F9AA8
- Gold: #D4AF37

## 10. Dark Mode

All components support `html[data-ui-mode="dark"]` via token overrides.
