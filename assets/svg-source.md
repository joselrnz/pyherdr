# PyHerdr — SVG Source Code

All assets inline, copy-paste ready. Palette: matte black `#0E1318`, Python blue
`#306998→#4B8BBE`, Python yellow `#FFD43B→#FFE873`, slate `#222B36`.
Font: JetBrains Mono (Fira Code / Cascadia Code / Consolas fallback).

## Usage snippets

```html
<!-- favicon -->
<link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
```

```markdown
<!-- README header -->
![PyHerdr](assets/banner.svg)

<!-- version badge -->
![version](assets/badge.svg)
```

```css
/* mono stencil recolors via currentColor */
.logo { color: #FFD43B; }
```


## banner.svg

```svg
<svg viewBox="0 0 1280 320" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="PyHerdr banner">
  <defs>
    <linearGradient id="blue3" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4B8BBE"/>
      <stop offset="100%" stop-color="#306998"/>
    </linearGradient>
    <linearGradient id="yellow3" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0%" stop-color="#FFD43B"/>
      <stop offset="100%" stop-color="#FFE873"/>
    </linearGradient>
    <linearGradient id="wm" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#4B8BBE"/>
      <stop offset="55%" stop-color="#6FA8D6"/>
      <stop offset="100%" stop-color="#FFD43B"/>
    </linearGradient>
  </defs>

  <!-- matte black, dead flat -->
  <rect width="1280" height="320" rx="24" fill="#0E1318"/>
  <rect x="2" y="2" width="1276" height="316" rx="22" fill="none" stroke="#1C242E" stroke-width="2"/>

  <!-- mini mark -->
  <g transform="translate(84,70)">
    <rect x="0" y="0" width="84" height="84" fill="url(#blue3)" rx="6"/>
    <circle cx="30" cy="30" r="8" fill="#F4F7FA"/>
    <rect x="96" y="0" width="62" height="84" fill="#1B232D" rx="6"/>
    <path d="M0 96 H84 L46 158 H0 Z" fill="url(#yellow3)"/>
    <g stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M100 104 L126 130 L100 156" stroke="#FFD43B" stroke-width="13"/>
      <line x1="134" y1="158" x2="158" y2="158" stroke="#4B8BBE" stroke-width="13"/>
    </g>
  </g>

  <!-- wordmark -->
  <text x="320" y="166" font-family="'JetBrains Mono','Fira Code','Cascadia Code',Consolas,monospace"
        font-size="86" font-weight="700" letter-spacing="3" fill="url(#wm)">PyHerdr</text>

  <!-- tagline -->
  <text x="324" y="216" font-family="'JetBrains Mono','Fira Code',Consolas,monospace"
        font-size="25" letter-spacing="2" fill="#7E8C9A">herd your terminals · multi-agent multiplexer</text>

  <!-- install pill -->
  <g transform="translate(324,242)" font-family="'JetBrains Mono',Consolas,monospace" font-size="21">
    <rect x="0" y="0" width="317" height="40" rx="20" fill="#161D25" stroke="#2A3542" stroke-width="1.5"/>
    <text x="22" y="27"><tspan fill="#FFD43B">$</tspan><tspan fill="#C7D2DC" dx="12">pip install pyherdr</tspan></text>
    <rect x="350" y="0" width="170" height="40" rx="20" fill="none" stroke="#306998" stroke-width="2"/>
    <text x="374" y="27" fill="#6FA8D6">python 3.12+</text>
  </g>
</svg>
```


## logo.svg

```svg
<svg viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="PyHerdr app icon">
  <defs>
    <linearGradient id="b" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4B8BBE"/><stop offset="100%" stop-color="#306998"/>
    </linearGradient>
    <linearGradient id="y" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0%" stop-color="#FFD43B"/><stop offset="100%" stop-color="#FFE873"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="100" fill="#0E1318"/>
  <rect x="3" y="3" width="506" height="506" rx="97" fill="none" stroke="#1C242E" stroke-width="2"/>
  <g transform="translate(83,83) scale(2.19)">
    <rect x="0" y="0" width="84" height="84" fill="url(#b)" rx="6"/>
    <circle cx="30" cy="30" r="8" fill="#F4F7FA"/>
    <rect x="96" y="0" width="62" height="84" fill="#1B232D" rx="6"/>
    <path d="M0 96 H84 L46 158 H0 Z" fill="url(#y)"/>
    <g stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M100 104 L126 130 L100 156" stroke="#FFD43B" stroke-width="13"/>
      <line x1="134" y1="158" x2="158" y2="158" stroke="#4B8BBE" stroke-width="13"/>
    </g>
  </g>
</svg>
```


## favicon.svg

```svg
<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="PyHerdr favicon">
  <rect width="64" height="64" rx="14" fill="#0E1318"/>
  <rect x="10" y="10" width="26" height="26" rx="3" fill="#4B8BBE"/>
  <path d="M10 40 H36 L24 58 H10 Z" fill="#FFD43B"/>
  <g stroke-linecap="round" stroke-linejoin="round" fill="none">
    <path d="M42 38 L50 46 L42 54" stroke="#FFD43B" stroke-width="6"/>
  </g>
  <rect x="42" y="10" width="12" height="26" rx="3" fill="#1B232D"/>
</svg>
```


## logo-light.svg

```svg
<svg viewBox="0 0 760 180" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="PyHerdr logo for light backgrounds">
  <defs>
    <linearGradient id="bl" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4B8BBE"/><stop offset="100%" stop-color="#306998"/>
    </linearGradient>
    <linearGradient id="yl" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0%" stop-color="#F5C518"/><stop offset="100%" stop-color="#FFD43B"/>
    </linearGradient>
  </defs>
  <g transform="translate(16,11)">
    <rect x="0" y="0" width="84" height="84" fill="url(#bl)" rx="6"/>
    <circle cx="30" cy="30" r="8" fill="#FFFFFF"/>
    <rect x="96" y="0" width="62" height="84" fill="#2A3542" rx="6"/>
    <path d="M0 96 H84 L46 158 H0 Z" fill="url(#yl)"/>
    <g stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M100 104 L126 130 L100 156" stroke="#E0A800" stroke-width="13"/>
      <line x1="134" y1="158" x2="158" y2="158" stroke="#306998" stroke-width="13"/>
    </g>
  </g>
  <text x="206" y="118" font-family="'JetBrains Mono','Fira Code',Consolas,monospace"
        font-size="78" font-weight="700" letter-spacing="2" fill="#1A2530">PyHerdr</text>
</svg>
```


## social-card.svg

```svg
<svg viewBox="0 0 1280 640" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="PyHerdr social card">
  <defs>
    <linearGradient id="bs" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4B8BBE"/><stop offset="100%" stop-color="#306998"/>
    </linearGradient>
    <linearGradient id="ys" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0%" stop-color="#FFD43B"/><stop offset="100%" stop-color="#FFE873"/>
    </linearGradient>
    <linearGradient id="wms" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#4B8BBE"/><stop offset="55%" stop-color="#6FA8D6"/><stop offset="100%" stop-color="#FFD43B"/>
    </linearGradient>
    <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M48 0 H0 V48" fill="none" stroke="#141C24" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="1280" height="640" fill="#0E1318"/>
  <rect width="1280" height="640" fill="url(#grid)"/>
  <!-- oversized wedge bleeding off the corner, quiet -->
  <path d="M-40 640 H300 L120 980 H-40 Z" fill="url(#ys)" opacity="0.10"/>
  <g transform="translate(120,150) scale(2.1)">
    <rect x="0" y="0" width="84" height="84" fill="url(#bs)" rx="6"/>
    <circle cx="30" cy="30" r="8" fill="#F4F7FA"/>
    <rect x="96" y="0" width="62" height="84" fill="#1B232D" rx="6"/>
    <path d="M0 96 H84 L46 158 H0 Z" fill="url(#ys)"/>
    <g stroke-linecap="round" stroke-linejoin="round" fill="none">
      <path d="M100 104 L126 130 L100 156" stroke="#FFD43B" stroke-width="13"/>
      <line x1="134" y1="158" x2="158" y2="158" stroke="#4B8BBE" stroke-width="13"/>
    </g>
  </g>
  <text x="540" y="300" font-family="'JetBrains Mono','Fira Code',Consolas,monospace"
        font-size="104" font-weight="700" letter-spacing="3" fill="url(#wms)">PyHerdr</text>
  <text x="546" y="362" font-family="'JetBrains Mono',Consolas,monospace"
        font-size="30" letter-spacing="2" fill="#7E8C9A">herd your terminals</text>
  <text x="546" y="406" font-family="'JetBrains Mono',Consolas,monospace"
        font-size="30" letter-spacing="2" fill="#7E8C9A">multi-agent multiplexer</text>
  <g transform="translate(546,448)" font-family="'JetBrains Mono',Consolas,monospace" font-size="24">
    <rect x="0" y="0" width="369" height="48" rx="24" fill="#161D25" stroke="#2A3542" stroke-width="1.5"/>
    <text x="26" y="32"><tspan fill="#FFD43B">$</tspan><tspan fill="#C7D2DC" dx="14">pip install pyherdr</tspan></text>
  </g>
</svg>
```


## mono.svg

```svg
<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="PyHerdr monochrome mark">
  <!-- single-color stencil: recolor via currentColor -->
  <g fill="currentColor" color="#F4F7FA">
    <path d="M20 20 H104 V104 H20 Z M50 58 a8 8 0 1 0 0.1 0 Z" fill-rule="evenodd" fill="currentColor"/>
    <rect x="116" y="20" width="62" height="84" rx="6" fill="none" stroke="currentColor" stroke-width="8"/>
    <path d="M20 116 H104 L66 178 H20 Z"/>
  </g>
  <g stroke="currentColor" color="#F4F7FA" stroke-linecap="round" stroke-linejoin="round" fill="none">
    <path d="M120 124 L146 150 L120 176" stroke-width="13"/>
    <line x1="154" y1="178" x2="178" y2="178" stroke-width="13"/>
  </g>
</svg>
```


## divider.svg

```svg
<svg viewBox="0 0 1280 36" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="PyHerdr section divider">
  <line x1="0" y1="18" x2="1216" y2="18" stroke="#2A3542" stroke-width="2"/>
  <path d="M1224 4 H1262 L1244 32 H1224 Z" fill="#FFD43B"/>
  <rect x="1188" y="8" width="22" height="22" rx="3" fill="#4B8BBE"/>
</svg>
```


## badge.svg

```svg
<svg viewBox="0 0 232 28" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="pyherdr version badge">
  <rect width="118" height="28" rx="4" fill="#1B232D"/>
  <rect x="118" width="114" height="28" rx="4" fill="#306998"/>
  <rect x="114" width="8" height="28" fill="#306998"/>
  <path d="M10 7 H22 L16 19 H10 Z" fill="#FFD43B"/>
  <g font-family="'JetBrains Mono',Consolas,monospace" font-size="14" fill="#C7D2DC">
    <text x="32" y="19">pyherdr</text>
    <text x="132" y="19" fill="#FFFFFF">v0.1.0 · py312</text>
  </g>
</svg>
```
