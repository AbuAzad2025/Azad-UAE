# Brand Guidelines — AZAD Intelligent Systems

## 1. Brand Identity

| Element | Value |
|---------|-------|
| Company name | AZAD Intelligent Systems |
| Arabic name | شركة أزاد للأنظمة الذكية |
| Product name | Azadexa ERP |
| Arabic product name | نظام أزادكسا |
| Tagline (EN) | Intelligent Systems for Intelligent Business |
| Tagline (AR) | أنظمة ذكية لأعمال ذكية |
| Founded | 2024 |
| Headquarters | Ramallah, Palestine |
| Primary market | UAE (Dubai, Abu Dhabi, Sharjah) |

## 2. Logo Usage

### 2.1 Primary Logo
- Full-color logo on white or light backgrounds.
- Dark logo (`logo-dark.png`) on colored or dark backgrounds.
- Minimum display width: 120 px digital, 20 mm print.

### 2.2 Clear Space
- Maintain clear space around the logo equal to the height of the "A" in "AZAD".

### 2.3 Logo Don'ts
- Do not stretch, distort, or rotate the logo.
- Do not change the logo colors.
- Do not place the logo on busy or low-contrast backgrounds.
- Do not add effects (shadows, glows, outlines).

### 2.4 File Locations
- `static/assets/brand/azad/logos/logo.png` — Primary
- `static/assets/brand/azad/logos/logo-dark.png` — Dark variant
- `static/assets/brand/azad/logos/logo-web.png` — Web-optimized
- `static/assets/brand/azad/logos/logo-mark.png` — Icon only

## 3. Color Palette

| Role | Hex | Usage |
|------|-----|-------|
| Primary | #667eea | Headers, CTAs, links, primary buttons |
| Primary hover | #5a6fd6 | Hover states |
| Secondary | #764ba2 | Accents, highlights, badges |
| Success | #28a745 | Success states, confirmations |
| Warning | #ffc107 | Alerts, pending actions |
| Danger | #dc3545 | Errors, deletions, critical alerts |
| Info | #17a2b8 | Informational messages |
| Dark | #2d3748 | Text, dark backgrounds |
| Light | #f8f9fa | Backgrounds, cards |
| White | #ffffff | Canvas, cards |

## 4. Typography

| Language | Font | Weights | Usage |
|----------|------|---------|-------|
| Arabic | Tajawal | 400, 500, 700, 800, 900 | All Arabic UI, reports, invoices |
| English | Inter or system-ui | 400, 500, 600, 700 | English UI, technical docs |
| Fallback | sans-serif | — | System fallback |

Font files: `static/fonts/tajawal/tajawal.css`

## 5. Tone of Voice

| Context | Tone | Example |
|---------|------|---------|
| UI labels | Direct, concise | "إنشاء فاتورة" / "Create Invoice" |
| Error messages | Helpful, blameless | "الكمية غير متوفرة. تحقق من المخزون." |
| Marketing | Confident, aspirational | "نظام أزادكسا: محاسبة ذكية لأعمالك" |
| Support | Empathetic, professional | "نحن هنا لمساعدتك. أرسل تفاصيل المشكلة." |
| AI responses | Informative, respectful | "التوصية: زيادة المخزون بنسبة 15%" |

## 6. Imagery and Photography

- Professional business photography: offices, warehouses, retail.
- No stock-photo clichés (handshakes, generic skyscrapers).
- People should reflect the target market: UAE business owners, accountants, cashiers, managers.
- Screenshots must use real Azadexa UI, not mockups.

## 7. Social Media Templates

| Platform | Dimensions | Primary Element |
|----------|------------|-----------------|
| LinkedIn | 1200×627 | Product screenshot + tagline |
| Instagram | 1080×1080 | Feature highlight + icon |
| Twitter/X | 1200×675 | News / update announcement |
| WhatsApp | 800×800 | Promotion / offer |

## 8. Legal Notices in Materials

Every public-facing material (digital or print) must include:
- "© 2026 AZAD Intelligent Systems. All Rights Reserved."
- Arabic: "© 2026 شركة أزاد للأنظمة الذكية. جميع الحقوق محفوظة."

Powered-by notice (for tenant-branded materials):
- "Powered by AZAD Intelligent Systems"

## 9. Application in Code

The brand is applied via `utils/tenant_branding.py`:
- `AZAD_LOGO` — platform logo path.
- `_POWERED_BY` — attribution text.
- `resolve_tenant_branding()` — returns all brand assets for a tenant.

## 10. Contact for Brand Inquiries

AZAD Intelligent Systems
Email: rafideen.ahmadghannam@gmail.com
