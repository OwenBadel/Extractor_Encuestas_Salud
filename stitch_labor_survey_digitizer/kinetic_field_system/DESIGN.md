---
name: Kinetic Field System
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#393939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353534'
  on-surface: '#e5e2e1'
  on-surface-variant: '#d5c4ab'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#9e8f78'
  outline-variant: '#514532'
  surface-tint: '#ffba20'
  primary: '#ffdca1'
  on-primary: '#412d00'
  primary-container: '#ffb800'
  on-primary-container: '#6b4c00'
  inverse-primary: '#7c5800'
  secondary: '#ffb59a'
  on-secondary: '#5a1b00'
  secondary-container: '#ff5e07'
  on-secondary-container: '#531900'
  tertiary: '#abebff'
  on-tertiary: '#003641'
  tertiary-container: '#00d7fe'
  on-tertiary-container: '#005a6b'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffdea8'
  primary-fixed-dim: '#ffba20'
  on-primary-fixed: '#271900'
  on-primary-fixed-variant: '#5e4200'
  secondary-fixed: '#ffdbce'
  secondary-fixed-dim: '#ffb59a'
  on-secondary-fixed: '#370e00'
  on-secondary-fixed-variant: '#802a00'
  tertiary-fixed: '#b0ecff'
  tertiary-fixed-dim: '#17d8ff'
  on-tertiary-fixed: '#001f27'
  on-tertiary-fixed-variant: '#004e5d'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353534'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
  data-lg:
    fontFamily: JetBrains Mono
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 8px
  touch-target: 48px
  gutter-md: 24px
  margin-edge: 32px
  container-max: 1440px
---

## Brand & Style
The design system is engineered for high-stakes field operations where environmental conditions are unpredictable and legibility is paramount. The brand personality is **utilitarian, resilient, and precise**. It targets field engineers, technicians, and logistics coordinators who require a "tools-not-toys" interface.

The design style is a hybrid of **Minimalism** and **Industrial Functionalism**. It prioritizes extreme clarity and ergonomic affordance over aesthetic flourish. Every element serves a functional purpose, utilizing a high-contrast foundation to ensure visibility under direct sunlight or low-light industrial settings. The emotional response should be one of total reliability and "ready-for-work" readiness.

## Colors
The palette is built on a "High-Visibility Industrial" logic. 

- **Primary (Solar Yellow):** Reserved strictly for critical primary actions and active states. It is designed to cut through visual noise.
- **Secondary (Industrial Orange):** Used for warnings, safety-related status indicators, and secondary high-priority actions.
- **Neutral (Carbon & Slate):** A deep charcoal base (#121212) minimizes glare in dark environments, while high-contrast grays define boundaries without adding bulk.
- **Functional Colors:** Success (Green) and Error (Red) use high-saturation tokens to ensure status is unmistakable at a glance.

The system defaults to **Dark Mode** to reduce eye strain and battery consumption on field tablets, but supports a high-contrast **Light Mode** (Pure White background) for direct-sunlight readability.

## Typography
The system utilizes **Inter** for its exceptional legibility and neutral tone. It is supplemented by **JetBrains Mono** for data readouts, status labels, and technical values to provide a distinct visual "texture" for machine-generated data vs. human-readable text.

- **Headlines:** Bold and tight-leading for immediate hierarchy.
- **Body:** Standardized at 16px to ensure accessibility on ruggedized handheld devices.
- **Labels:** Monospaced and uppercase to evoke industrial stamping and technical specifications.
- **Data:** Numerical values are always monospaced to prevent layout shifting when values update in real-time.

## Layout & Spacing
The layout follows a **Rigid Grid System** designed for "gloved-hand" ergonomics. 

- **Grid Model:** 12-column fluid grid on desktop; 4-column on mobile.
- **Spacing Rhythm:** Based on an 8px base unit. All interactive elements must maintain a minimum 48px height/width touch target to accommodate field use.
- **Safe Areas:** Large 32px outer margins ensure content is not obscured by ruggedized device cases or physical screen protectors.
- **Reflow:** On mobile, sidebars collapse into a persistent bottom navigation bar for thumb-first interaction.

## Elevation & Depth
In this design system, depth is communicated through **Tonal Layering** and **Low-Contrast Outlines** rather than soft shadows. 

- **Surfaces:** Use three tiers of "Carbon" (Base: #121212, Surface: #1E1E1E, Elevated: #2A2A2A).
- **Borders:** Instead of shadows, use 1px or 2px solid strokes (#333333) to define boundaries. This ensures shapes remain crisp even on low-quality outdoor displays.
- **Active State:** Physical "pressed" effects are simulated by changing the stroke weight or reversing the background/foreground colors (Inversion).

## Shapes
The shape language is **Soft (0.25rem)**. This provides a balance between the "hard" nature of industrial equipment and the modern digital interface. 

- **Small elements (Checkboxes/Tags):** 4px radius.
- **Large elements (Cards/Buttons):** 8px radius.
- **Status Indicators:** Icons and status dots remain sharp (0px) to signify technical precision.

## Components
- **Buttons:** Large, high-contrast blocks. Primary buttons use #FFB800 with black text. Ghost buttons use a 2px stroke. All buttons have a defined "active" state that fills the container.
- **Cards:** High-contrast containers with internal 24px padding. Headers are separated by a 1px divider to keep data organized.
- **Progress Bars:** "Industrial-grade" thick bars (12px height). The track is a dark neutral (#2A2A2A) and the fill is the primary color or green. Include segment notches for specific milestones.
- **Status Indicators:** Use "Pending" (Outline + Monospaced text) and "Sent" (Solid Fill + Monospaced text) treatments.
- **Input Fields:** Thick borders (2px) and high-contrast focus states. Labels are always visible (never floating) to prevent context loss during data entry.
- **Data Grid:** Tight rows with alternating zebra striping (#181818 / #121212) for scanning long lists of telemetry or asset data.