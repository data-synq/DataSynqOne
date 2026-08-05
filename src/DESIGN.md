# DESIGN.md

## 1. Purpose

This document defines a modern visual system for a real-estate and property-services website.

The original pastel color identity is retained, while the composition, typography, interaction design and depth system are modernized.

The result should feel:

- trustworthy and calm
- contemporary and premium
- warm rather than clinical
- visually spacious
- editorial rather than template-like
- suitable for real estate, property management and assisted living

Reference identity:

`https://www.laenger-immobilien.com/`

The implementation must be inspired by the brand character, not reproduce the reference website pixel by pixel.

---

## 2. Modern Design Direction

### Core concept

**Modern residential editorial**

The website combines the reliability of a regional property company with the visual quality of a contemporary architecture magazine.

The design uses:

- asymmetric layouts
- large editorial typography
- layered image compositions
- soft depth and subtle transparency
- modern card grids
- generous spacing
- restrained motion
- warm pastel gradients derived from the existing brand palette

### Visual keywords

`architectural` · `editorial` · `calm` · `human` · `premium` · `regional` · `accessible`

### Replace the old visual patterns

| Old pattern | Modern replacement |
|---|---|
| Thin utility bar | Compact contact actions integrated into the header |
| Centered logo and menu | Wide sticky navigation with clear hierarchy |
| Full-width image followed by centered text | Layered split hero with floating content panel |
| Three identical service columns | Asymmetric Bento grid |
| Flat white sections | Layered surfaces with subtle tonal changes |
| Small light typography | Larger, stronger editorial hierarchy |
| Plain rectangular cards | Soft-radius cards with image depth and hover movement |
| Static content flow | Controlled overlap and visual rhythm |
| Almost no effects | Subtle blur, gradients, shadows and motion |
| Generic footer row | Structured modern footer with clear contact CTA |

### Avoid

- excessive glassmorphism
- saturated blue or gold
- dark luxury styling
- large glossy gradients
- floating elements without purpose
- heavy shadows
- excessive animation
- generic SaaS dashboard styling
- identical cards in every section
- tiny light-gray text

---

## 3. Brand Colors

The recognizable pastel palette remains unchanged. Modernity comes from better contrast, gradients, layering and surface combinations.

```css
:root {
  /* Existing brand identity */
  --color-brand-blue: #a8c5d2;
  --color-brand-blue-strong: #83afc2;
  --color-brand-blue-dark: #587d8d;

  --color-brand-gold: #d7c394;
  --color-brand-gold-dark: #b59d68;

  --color-cream: #e8e0c8;
  --color-cream-light: #f4f0e4;

  /* Modern neutral system */
  --color-white: #ffffff;
  --color-canvas: #f8faf9;
  --color-surface: #ffffff;
  --color-surface-blue: #eef4f6;
  --color-surface-warm: #f6f2e8;
  --color-surface-deep: #e4edf0;

  /* Text */
  --color-text: #46545b;
  --color-text-soft: #718087;
  --color-heading: #456774;
  --color-heading-strong: #304f5b;

  /* Functional */
  --color-border: rgba(88, 125, 141, 0.16);
  --color-border-strong: rgba(88, 125, 141, 0.28);
  --color-focus: #4f8fa8;
  --color-error: #a8443b;
  --color-success: #527661;

  /* Transparent surfaces */
  --surface-glass: rgba(255, 255, 255, 0.76);
  --surface-glass-strong: rgba(255, 255, 255, 0.9);

  /* Gradients */
  --gradient-brand:
    linear-gradient(
      135deg,
      rgba(168, 197, 210, 0.95),
      rgba(232, 224, 200, 0.9)
    );

  --gradient-soft-blue:
    radial-gradient(
      circle at 20% 20%,
      rgba(168, 197, 210, 0.42),
      transparent 55%
    );

  --gradient-soft-gold:
    radial-gradient(
      circle at 80% 30%,
      rgba(215, 195, 148, 0.28),
      transparent 50%
    );
}
```

### Color rules

- White remains the primary reading surface.
- Cream is used for warmth, not as a permanent page background.
- Pastel blue defines navigation, interaction and architectural accents.
- Gold is used sparingly for labels, small details and visual balance.
- Important text always uses darker blue-gray tones.
- Gradients must use only existing brand colors and remain subtle.

### Recommended page background

```css
body {
  background:
    var(--gradient-soft-blue),
    var(--gradient-soft-gold),
    var(--color-canvas);
}
```

---

## 4. Typography

The typography should feel contemporary and architectural.

### Font pairing

Use **Manrope** for headings and UI elements, and **Inter** for longer body text.

```css
:root {
  --font-display: "Manrope", "Avenir Next", "Segoe UI", sans-serif;
  --font-body: "Inter", "Helvetica Neue", Arial, sans-serif;
}
```

Both fonts should be self-hosted where possible.

### Weight system

- `400`: body text
- `500`: navigation and controls
- `600`: card titles and compact headings
- `700`: hero emphasis and key statistics

Do not rely on extremely thin font weights. The old lightweight appearance should be replaced with clearer visual hierarchy.

### Fluid type scale

```css
:root {
  --font-size-xs: 0.75rem;
  --font-size-sm: 0.875rem;
  --font-size-base: clamp(1rem, 0.97rem + 0.12vw, 1.075rem);
  --font-size-lg: clamp(1.125rem, 1.05rem + 0.3vw, 1.3rem);
  --font-size-xl: clamp(1.4rem, 1.2rem + 0.65vw, 1.8rem);
  --font-size-2xl: clamp(2rem, 1.55rem + 1.5vw, 3rem);
  --font-size-3xl: clamp(3rem, 2rem + 3.6vw, 6rem);

  --line-height-tight: 1.02;
  --line-height-heading: 1.15;
  --line-height-body: 1.68;
}
```

### Heading treatment

```css
h1,
h2,
h3 {
  margin: 0;
  color: var(--color-heading-strong);
  font-family: var(--font-display);
  text-wrap: balance;
}

h1 {
  max-width: 12ch;
  font-size: var(--font-size-3xl);
  font-weight: 650;
  letter-spacing: -0.045em;
  line-height: var(--line-height-tight);
}

h2 {
  max-width: 18ch;
  font-size: var(--font-size-2xl);
  font-weight: 620;
  letter-spacing: -0.03em;
  line-height: var(--line-height-heading);
}

h3 {
  font-size: var(--font-size-xl);
  font-weight: 600;
  letter-spacing: -0.02em;
}
```

### Eyebrow label

Small labels add structure above headings.

```css
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 1rem;
  color: var(--color-brand-blue-dark);
  font-family: var(--font-display);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}

.eyebrow::before {
  width: 2rem;
  height: 1px;
  background: var(--color-brand-gold-dark);
  content: "";
}
```

### Text width

- Body text: maximum `66ch`
- Introductory lead: maximum `52ch`
- Hero support text: maximum `42ch`

---

## 5. Layout System

### Container widths

```css
:root {
  --content-width: 1280px;
  --content-wide: 1480px;
  --content-narrow: 760px;
  --page-padding: clamp(1.25rem, 4vw, 4.5rem);
}
```

```css
.container {
  width: min(
    calc(100% - (2 * var(--page-padding))),
    var(--content-width)
  );
  margin-inline: auto;
}

.container--wide {
  width: min(
    calc(100% - (2 * var(--page-padding))),
    var(--content-wide)
  );
  margin-inline: auto;
}
```

### Spacing system

```css
:root {
  --space-1: 0.5rem;
  --space-2: 0.75rem;
  --space-3: 1rem;
  --space-4: 1.5rem;
  --space-5: 2rem;
  --space-6: 3rem;
  --space-7: 4.5rem;
  --space-8: 6.5rem;
  --space-9: 9rem;
}
```

### Radius system

```css
:root {
  --radius-sm: 10px;
  --radius-md: 16px;
  --radius-lg: 24px;
  --radius-xl: 36px;
  --radius-pill: 999px;
}
```

### Shadow system

```css
:root {
  --shadow-sm:
    0 1px 2px rgba(48, 79, 91, 0.04),
    0 8px 24px rgba(48, 79, 91, 0.06);

  --shadow-md:
    0 2px 4px rgba(48, 79, 91, 0.04),
    0 18px 50px rgba(48, 79, 91, 0.1);

  --shadow-lg:
    0 12px 30px rgba(48, 79, 91, 0.08),
    0 40px 90px rgba(48, 79, 91, 0.13);
}
```

Shadows should be wide and soft, never black and hard.

---

## 6. Page Rhythm

The website should not look like a sequence of identical horizontal rectangles.

Use a rhythm of:

1. Full-width layered hero
2. Overlapping trust or service panel
3. Large editorial introduction
4. Asymmetric service grid
5. Image-led split section
6. Property or location showcase
7. Warm contact CTA
8. Structured footer

### Section spacing

```css
.section {
  padding-block: clamp(4.5rem, 9vw, 9rem);
}

.section--compact {
  padding-block: clamp(3rem, 6vw, 5.5rem);
}
```

### Controlled overlap

Sections may overlap by `40–100px` where it strengthens the composition.

```css
.section--overlap {
  position: relative;
  z-index: 2;
  margin-top: clamp(-6rem, -8vw, -3rem);
}
```

Do not overlap text directly over busy imagery without a clear surface.

---

## 7. Header and Navigation

The old utility bar should be removed. Phone and email actions move into the main header.

### Header behavior

- sticky at the top
- transparent over the hero initially
- becomes a blurred white surface after scrolling
- height reduces slightly after scrolling
- logo remains clearly visible
- contact action appears as a compact button

```css
.site-header {
  position: fixed;
  z-index: 100;
  top: 0;
  left: 0;
  width: 100%;
  transition:
    background-color 220ms ease,
    box-shadow 220ms ease,
    backdrop-filter 220ms ease;
}

.site-header[data-scrolled="true"] {
  background: var(--surface-glass);
  box-shadow: 0 1px 0 var(--color-border);
  backdrop-filter: blur(18px) saturate(140%);
}

.site-header__inner {
  display: grid;
  grid-template-columns: auto 1fr auto;
  min-height: 88px;
  align-items: center;
  gap: 2rem;
}
```

### Navigation

```css
.main-nav {
  display: flex;
  justify-content: center;
  gap: clamp(1.25rem, 2.6vw, 2.75rem);
}

.main-nav a {
  position: relative;
  color: var(--color-heading-strong);
  font-family: var(--font-display);
  font-size: 0.9rem;
  font-weight: 550;
  text-decoration: none;
}

.main-nav a::after {
  position: absolute;
  right: 0;
  bottom: -0.55rem;
  left: 0;
  height: 2px;
  border-radius: 2px;
  background: var(--color-brand-blue-strong);
  content: "";
  transform: scaleX(0);
  transform-origin: right;
  transition: transform 220ms ease;
}

.main-nav a:hover::after,
.main-nav a[aria-current="page"]::after {
  transform: scaleX(1);
  transform-origin: left;
}
```

### Contact button in header

```css
.header-contact {
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  gap: 0.55rem;
  padding: 0.65rem 1rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-pill);
  background: var(--surface-glass-strong);
  color: var(--color-heading-strong);
  font-family: var(--font-display);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
  backdrop-filter: blur(12px);
}
```

### Mobile navigation

Use a right-side drawer with:

- white blurred surface
- large navigation links
- visible contact actions
- reduced visual noise
- no dark full-screen takeover

---

## 8. Hero Section

The hero should become the strongest modernization element.

### Recommended composition

Desktop:

```text
┌──────────────────────────────────────────────────────────┐
│ Header                                                   │
│                                                          │
│ Large editorial heading        ┌───────────────────────┐ │
│ Supporting text                │                       │ │
│ Primary + text action          │  architectural image │ │
│                                │                       │ │
│          small trust chip      └───────────────────────┘ │
│                    secondary image overlap                │
└──────────────────────────────────────────────────────────┘
```

The hero is not a single image with centered text. It is a responsive two-column composition with layered media.

### Hero background

```css
.hero {
  position: relative;
  min-height: min(920px, 100svh);
  overflow: clip;
  padding-top: 8rem;
  background:
    radial-gradient(
      circle at 10% 20%,
      rgba(168, 197, 210, 0.42),
      transparent 42%
    ),
    radial-gradient(
      circle at 80% 10%,
      rgba(215, 195, 148, 0.25),
      transparent 34%
    ),
    var(--color-canvas);
}

.hero::before {
  position: absolute;
  top: 8%;
  right: -8%;
  width: min(42vw, 680px);
  aspect-ratio: 1;
  border-radius: 50%;
  background: rgba(168, 197, 210, 0.18);
  filter: blur(2px);
  content: "";
}
```

### Hero grid

```css
.hero__inner {
  display: grid;
  min-height: calc(100svh - 8rem);
  grid-template-columns: minmax(0, 0.85fr) minmax(520px, 1.15fr);
  align-items: center;
  gap: clamp(3rem, 7vw, 8rem);
}
```

### Hero media

```css
.hero-media {
  position: relative;
  min-height: 660px;
}

.hero-media__primary {
  position: absolute;
  top: 0;
  right: 0;
  width: 84%;
  height: 82%;
  overflow: hidden;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
}

.hero-media__secondary {
  position: absolute;
  bottom: 1rem;
  left: 0;
  width: 46%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border: 10px solid rgba(255, 255, 255, 0.8);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(12px);
}
```

### Hero trust chip

Use one floating information element, for example:

```text
Personally managed
Regional expertise
Reliable since 19XX
```

```css
.trust-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.74);
  box-shadow: var(--shadow-sm);
  color: var(--color-heading-strong);
  font-size: var(--font-size-sm);
  font-weight: 600;
  backdrop-filter: blur(14px);
}
```

### Mobile hero

- heading and actions appear first
- main image appears below
- secondary image becomes a small overlapping card
- minimum hero height should not be forced to full viewport
- decorative gradients remain subtle

---

## 9. Buttons and Interactive Links

### Primary button

```css
.button--primary {
  display: inline-flex;
  min-height: 50px;
  align-items: center;
  justify-content: center;
  gap: 0.65rem;
  padding: 0.85rem 1.35rem;
  border: 1px solid var(--color-brand-blue-dark);
  border-radius: var(--radius-pill);
  background: var(--color-brand-blue-dark);
  box-shadow: 0 10px 28px rgba(88, 125, 141, 0.22);
  color: var(--color-white);
  font-family: var(--font-display);
  font-size: 0.925rem;
  font-weight: 650;
  text-decoration: none;
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease;
}

.button--primary:hover {
  background: var(--color-heading-strong);
  box-shadow: 0 14px 34px rgba(48, 79, 91, 0.26);
  transform: translateY(-2px);
}
```

### Secondary button

```css
.button--secondary {
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.68);
  color: var(--color-heading-strong);
  backdrop-filter: blur(12px);
}
```

### Arrow link

```css
.arrow-link {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  color: var(--color-brand-blue-dark);
  font-family: var(--font-display);
  font-weight: 650;
  text-decoration: none;
}

.arrow-link svg {
  transition: transform 180ms ease;
}

.arrow-link:hover svg {
  transform: translateX(4px);
}
```

---

## 10. Intro and Trust Panel

Instead of a centered text block, use a two-column editorial introduction.

```css
.intro-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
  align-items: start;
  gap: clamp(2.5rem, 8vw, 8rem);
}
```

Left:

- eyebrow
- large heading

Right:

- lead paragraph
- one short supporting paragraph
- optional text link

### Floating trust panel

Place a compact panel between the hero and intro section.

```css
.trust-panel {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.85);
  border-radius: var(--radius-lg);
  background: var(--surface-glass-strong);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(20px);
}

.trust-panel__item {
  padding: 1.5rem 1.75rem;
}

.trust-panel__item + .trust-panel__item {
  border-left: 1px solid var(--color-border);
}
```

Possible items:

- Personal contact
- Regional experience
- Reliable management

Do not invent statistics unless they are verified.

---

## 11. Service Bento Grid

The three equal columns should be replaced by a more dynamic Bento layout.

### Desktop structure

```text
┌───────────────────────┬───────────────┐
│                       │ Assisted      │
│ Property management   │ living        │
│ large image card      ├───────────────┤
│                       │ Rentals       │
└───────────────────────┴───────────────┘
```

```css
.service-bento {
  display: grid;
  grid-template-columns: 1.35fr 0.65fr;
  grid-template-rows: repeat(2, minmax(260px, 1fr));
  gap: 1.25rem;
}

.service-card:first-child {
  grid-row: 1 / 3;
}
```

### Card style

```css
.service-card {
  position: relative;
  min-height: 280px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-sm);
  isolation: isolate;
  transition:
    transform 240ms ease,
    box-shadow 240ms ease;
}

.service-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-6px);
}

.service-card__image {
  position: absolute;
  z-index: -2;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 600ms cubic-bezier(0.2, 0, 0, 1);
}

.service-card:hover .service-card__image {
  transform: scale(1.045);
}

.service-card::after {
  position: absolute;
  z-index: -1;
  inset: 0;
  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.04) 20%,
      rgba(48, 79, 91, 0.72) 100%
    );
  content: "";
}

.service-card__content {
  display: flex;
  min-height: inherit;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-end;
  padding: clamp(1.5rem, 4vw, 2.5rem);
  color: var(--color-white);
}
```

For lighter cards, replace the image background with a pastel surface and a cropped architectural detail.

---

## 12. Feature and Process Cards

Secondary information should use modern soft cards.

```css
.feature-card {
  padding: clamp(1.5rem, 3vw, 2.25rem);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(10px);
}
```

### Icon container

```css
.feature-card__icon {
  display: grid;
  width: 48px;
  height: 48px;
  margin-bottom: 1.5rem;
  place-items: center;
  border-radius: 14px;
  background: var(--color-surface-blue);
  color: var(--color-brand-blue-dark);
}
```

Avoid large icon circles and generic stock illustrations.

---

## 13. Image-Led Split Sections

Use split layouts with unequal columns and controlled overlap.

```css
.editorial-split {
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(0, 0.88fr);
  align-items: center;
  gap: clamp(3rem, 8vw, 8rem);
}
```

### Image stack

```css
.image-stack {
  position: relative;
  min-height: 620px;
}

.image-stack__main {
  width: 82%;
  height: 88%;
  overflow: hidden;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
}

.image-stack__accent {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 46%;
  aspect-ratio: 1;
  overflow: hidden;
  border: 8px solid var(--color-canvas);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}
```

Alternate media placement between sections to create rhythm.

---

## 14. Property and Location Showcase

Properties should be presented as editorial stories, not database records.

### Featured property card

```css
.property-card {
  display: grid;
  overflow: hidden;
  grid-template-columns: minmax(0, 1.25fr) minmax(340px, 0.75fr);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  background: var(--color-surface);
  box-shadow: var(--shadow-md);
}

.property-card__media {
  min-height: 520px;
}

.property-card__content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: clamp(2rem, 5vw, 4.5rem);
}
```

### Property facts

Use compact rounded information cells.

```css
.property-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  margin-block: 1.5rem;
}

.property-fact {
  padding: 0.65rem 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface-blue);
  color: var(--color-heading-strong);
  font-size: var(--font-size-sm);
  font-weight: 600;
}
```

---

## 15. Gallery

Use one large visual and a small set of supporting images.

```css
.gallery {
  display: grid;
  grid-template-columns: 1.5fr 0.75fr 0.75fr;
  grid-template-rows: repeat(2, minmax(220px, 1fr));
  gap: 1rem;
}

.gallery__item {
  overflow: hidden;
  border-radius: var(--radius-md);
}

.gallery__item:first-child {
  grid-row: 1 / 3;
}
```

All image cards should:

- use consistent corner radii
- have restrained hover zoom
- open in an accessible lightbox
- preserve keyboard navigation
- show meaningful captions only where needed

---

## 16. Forms

Forms should feel simple and premium, not administrative.

### Form surface

```css
.contact-form {
  padding: clamp(1.5rem, 4vw, 3.5rem);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.82);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(18px);
}
```

### Field layout

```css
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1.4rem;
}

.form-field--full {
  grid-column: 1 / -1;
}
```

### Inputs

```css
input,
select,
textarea {
  width: 100%;
  min-height: 52px;
  padding: 0.85rem 1rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.9);
  color: var(--color-text);
  font: inherit;
  transition:
    border-color 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease;
}

textarea {
  min-height: 180px;
  resize: vertical;
}

input:focus,
select:focus,
textarea:focus {
  border-color: var(--color-focus);
  background: var(--color-white);
  box-shadow: 0 0 0 4px rgba(79, 143, 168, 0.14);
  outline: none;
}
```

Labels remain visible above fields. Placeholders never replace labels.

---

## 17. Contact CTA

The final CTA should be visually distinct and modern.

### Recommended layout

- large rounded container
- soft brand gradient
- heading and supporting text on the left
- contact actions on the right
- optional subtle architectural line graphic in the background

```css
.contact-cta {
  position: relative;
  display: grid;
  overflow: hidden;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 3rem;
  padding: clamp(2.5rem, 6vw, 5rem);
  border-radius: var(--radius-xl);
  background: var(--gradient-brand);
  box-shadow: var(--shadow-md);
}

.contact-cta::after {
  position: absolute;
  right: -10%;
  bottom: -60%;
  width: 420px;
  aspect-ratio: 1;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 50%;
  content: "";
}
```

---

## 18. Footer

Use a structured footer instead of a single narrow legal row.

### Layout

```text
Logo and short brand statement
Navigation
Services
Contact
Legal links
```

```css
.site-footer {
  margin-top: clamp(5rem, 10vw, 10rem);
  padding-top: clamp(4rem, 8vw, 7rem);
  background: var(--color-heading-strong);
  color: rgba(255, 255, 255, 0.78);
}

.site-footer__grid {
  display: grid;
  grid-template-columns: 1.4fr repeat(3, 0.7fr);
  gap: clamp(2rem, 5vw, 5rem);
}

.site-footer a {
  color: rgba(255, 255, 255, 0.78);
  text-decoration: none;
}

.site-footer a:hover {
  color: var(--color-white);
}
```

The dark blue-gray footer uses an existing brand-derived tone and creates a modern visual ending without introducing a new color family.

---

## 19. Decorative Effects

Decorative effects must remain architectural and restrained.

### Allowed

- blurred pastel gradient fields
- thin architectural line graphics
- large soft circles behind imagery
- cropped grid patterns
- subtle grain at very low opacity
- soft glass surfaces
- controlled image overlap
- large corner radii
- wide soft shadows

### Example background ornament

```css
.decorative-grid {
  background-image:
    linear-gradient(
      rgba(88, 125, 141, 0.07) 1px,
      transparent 1px
    ),
    linear-gradient(
      90deg,
      rgba(88, 125, 141, 0.07) 1px,
      transparent 1px
    );
  background-size: 40px 40px;
}
```

Use grid patterns only in small decorative areas, never behind long body text.

---

## 20. Motion

Motion should make the interface feel polished, not animated.

### Timing tokens

```css
:root {
  --duration-fast: 160ms;
  --duration-normal: 240ms;
  --duration-slow: 600ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-emphasized: cubic-bezier(0.16, 1, 0.3, 1);
}
```

### Recommended effects

- navigation underline
- button lift of `1–2px`
- card lift of `4–6px`
- image zoom up to `1.045`
- content reveal with `opacity` and `translateY(16px)`
- header blur after scrolling
- staggered reveal for service cards

### Reveal animation

```css
.reveal {
  opacity: 0;
  transform: translateY(18px);
  transition:
    opacity 650ms var(--ease-emphasized),
    transform 650ms var(--ease-emphasized);
}

.reveal[data-visible="true"] {
  opacity: 1;
  transform: translateY(0);
}
```

Avoid:

- automatic carousels
- continuous floating motion
- aggressive parallax
- bouncing controls
- page transitions longer than `500ms`

### Reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 21. Responsive Design

### Breakpoints

```css
:root {
  --breakpoint-sm: 480px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1024px;
  --breakpoint-xl: 1280px;
}
```

### Tablet

Below `1024px`:

- hero becomes a balanced vertical layout
- Bento grid may remain two columns
- header contact text can be shortened
- overlapping images are reduced
- content spacing becomes more compact

### Mobile

Below `768px`:

```css
@media (max-width: 767px) {
  .hero__inner,
  .intro-grid,
  .editorial-split,
  .property-card,
  .contact-cta,
  .site-footer__grid {
    grid-template-columns: 1fr;
  }

  .service-bento {
    grid-template-columns: 1fr;
    grid-template-rows: none;
  }

  .service-card:first-child {
    grid-row: auto;
  }

  .trust-panel {
    grid-template-columns: 1fr;
  }

  .trust-panel__item + .trust-panel__item {
    border-top: 1px solid var(--color-border);
    border-left: 0;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .hero-media {
    min-height: 470px;
  }
}
```

Mobile rules:

- side padding of at least `20px`
- touch targets of at least `44px`
- large text remains balanced without oversized empty areas
- overlap is reduced, not removed completely
- cards maintain `16–24px` corner radii
- horizontal scroll must never occur

---

## 22. Accessibility

Minimum target: **WCAG 2.2 AA**

Requirements:

- visible keyboard focus
- semantic heading hierarchy
- body text at least `16px`
- meaningful alternative text
- form labels connected with `for` and `id`
- error messages connected through `aria-describedby`
- no information communicated by color alone
- no essential text directly over unprotected images
- reduced-motion support
- minimum touch target of `44 × 44px`
- sufficient contrast despite the pastel palette
- mobile menu usable by keyboard and screen reader
- blur and transparency must have an opaque fallback

The light blue and gold colors are decorative. Small text and controls must use darker blue-gray variants.

---

## 23. Image Direction

### Preferred photography

- modern but believable residential buildings
- natural daylight
- landscaped gardens
- accessible paths and entrances
- warm neutral façades
- regional context
- real employees or residents in candid situations
- architectural details such as doors, balconies and materials

### Editing

- natural color balance
- slightly warm highlights
- moderate contrast
- no heavy HDR
- restrained saturation
- maintain detail in white façades and sky
- consistent image grading across the site

### Cropping

- use wide cinematic crops in hero and featured property areas
- use square crops for small detail cards
- preserve architectural lines
- leave enough negative space around text-adjacent subjects

---

## 24. Iconography

Recommended libraries:

- Lucide
- Phosphor
- custom architectural SVG icons

Rules:

- stroke width: `1.5–2px`
- rounded line caps
- sizes between `18px` and `28px`
- icons should sit in small soft containers where emphasis is needed
- do not combine multiple icon styles
- avoid generic 3D illustrations

---

## 25. Content Tone

The tone should be:

- personal
- clear
- reliable
- regional
- reassuring
- direct

Prefer:

> We take care of your property personally, transparently and with a clear eye for long-term value.

Avoid:

> We revolutionize the real-estate market with disruptive full-service solutions.

### Content rules

- use short paragraphs
- lead with user benefit
- explain services without legal or administrative jargon
- keep calls to action concrete
- use real proof instead of inflated claims
- avoid repeated welcome phrases

---

## 26. Component Library

```text
SiteHeader
BrandLogo
DesktopNavigation
MobileNavigation
HeaderContactAction
HeroEditorial
HeroMediaStack
TrustChip
TrustPanel
EyebrowLabel
SectionHeader
IntroEditorial
ServiceBento
ServiceCard
FeatureCard
EditorialSplit
ImageStack
FeaturedPropertyCard
PropertyFacts
Gallery
ContactForm
PrimaryButton
SecondaryButton
ArrowLink
ContactCTA
SiteFooter
CookieConsent
```

### Component principle

Every major component should have:

- one clear purpose
- one dominant visual hierarchy
- meaningful spacing
- a responsive fallback
- no hard-coded color values
- accessible hover, focus and disabled states

---

## 27. Recommended Technical Implementation

Suggested stack:

```text
Framework: Astro or Next.js
Styling: CSS Modules, Sass or Tailwind with custom design tokens
Fonts: self-hosted Manrope and Inter
Icons: Lucide
Images: AVIF/WebP with responsive srcset
Motion: CSS and IntersectionObserver
Forms: server-side validation with accessible client feedback
```

### CSS structure

```text
styles/
├── tokens.css
├── reset.css
├── base.css
├── typography.css
├── layout.css
├── effects.css
├── utilities.css
└── components/
    ├── header.css
    ├── navigation.css
    ├── hero.css
    ├── trust-panel.css
    ├── service-bento.css
    ├── editorial-split.css
    ├── property-card.css
    ├── gallery.css
    ├── forms.css
    ├── contact-cta.css
    └── footer.css
```

Use native CSS features such as:

- `clamp()`
- `min()`
- `max()`
- `aspect-ratio`
- `object-fit`
- `text-wrap: balance`
- container queries where useful
- `prefers-reduced-motion`

---

## 28. Homepage Blueprint

```text
1. Sticky transparent header
   - Logo
   - Main navigation
   - Compact contact action

2. Editorial hero
   - Eyebrow label
   - Large headline
   - Short supporting text
   - Primary and secondary actions
   - Layered architecture images
   - One trust chip

3. Overlapping trust panel
   - Three concise service promises

4. Editorial introduction
   - Large heading on the left
   - Explanatory text on the right

5. Service Bento grid
   - Large property-management card
   - Assisted-living card
   - Rentals card

6. Image-led company section
   - Layered photographs
   - Personal regional positioning
   - Text link

7. Featured property or location
   - Large rounded split card
   - Compact property facts

8. Contact CTA
   - Warm pastel gradient
   - Clear contact actions

9. Structured dark footer
```

---

## 29. Modernization Checklist

- [ ] The original pastel blue, cream and gold identity is recognizable.
- [ ] The page no longer consists of repeated full-width text sections.
- [ ] The hero uses an asymmetric composition.
- [ ] The header becomes translucent and sticky after scrolling.
- [ ] Service areas use a Bento grid instead of equal columns.
- [ ] Cards use soft radius, subtle shadow and restrained hover motion.
- [ ] Images overlap selectively to create depth.
- [ ] Typography is larger, stronger and more editorial.
- [ ] Gradients use only existing brand colors.
- [ ] Text remains clearly readable despite transparent surfaces.
- [ ] Mobile layouts preserve hierarchy and depth.
- [ ] Effects improve orientation instead of becoming decoration.
- [ ] The website feels like a contemporary architecture brand, not a legacy business template.
- [ ] Accessibility and reduced-motion behavior are implemented.

---

## 30. One-Sentence Design Rule

> Preserve the calm pastel identity, but present it through asymmetric editorial layouts, layered architectural imagery, soft translucent surfaces, modern typography and carefully controlled depth.
