<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'hero' | 'empty' | 'path' | 'side' }>(), { variant: 'hero' })
</script>

<template>
  <div class="learning-atmosphere" :class="`is-${variant}`" aria-hidden="true">
    <svg viewBox="0 0 640 280" role="presentation">
      <defs>
        <linearGradient id="atmo-sky" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#e9f8ff"/><stop offset="1" stop-color="#effcf5"/></linearGradient>
        <linearGradient id="atmo-blue" x1="0" x2="1"><stop offset="0" stop-color="#55b9ed"/><stop offset="1" stop-color="#6375e8"/></linearGradient>
        <linearGradient id="atmo-mint" x1="0" x2="1"><stop offset="0" stop-color="#7ddac1"/><stop offset="1" stop-color="#bceecf"/></linearGradient>
        <filter id="atmo-shadow" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="10" flood-color="#5181a8" flood-opacity=".16" stdDeviation="9"/></filter>
      </defs>

      <g v-if="variant === 'hero'">
        <rect x="28" y="22" width="584" height="230" rx="38" fill="url(#atmo-sky)"/>
        <path d="M60 211c50-31 73-6 113-21 47-18 71-66 123-53 44 11 49 48 94 47 43-1 64-36 127-19 31 8 54 28 69 46H60Z" fill="#dff5ed"/>
        <g class="atmo-stars" fill="#f4c45d"><circle cx="91" cy="75" r="5"/><circle cx="542" cy="69" r="4"/><circle cx="501" cy="185" r="3"/></g>
        <g class="atmo-float" transform="translate(76 52) rotate(-8)"><rect width="104" height="72" rx="12" fill="#fff" filter="url(#atmo-shadow)"/><rect x="15" y="16" width="46" height="7" rx="4" fill="#b9d9f4"/><rect x="15" y="31" width="70" height="6" rx="3" fill="#dbeaf5"/><path d="M18 58h13V45h10v13h12V38h10v20h13" fill="none" stroke="#69c9b2" stroke-linecap="round" stroke-linejoin="round" stroke-width="5"/></g>
        <g class="atmo-float" transform="translate(458 38) rotate(9)"><path d="M0 25 62 0l18 45-62 25Z" fill="#fff" filter="url(#atmo-shadow)"/><path d="m14 27 43-17M18 39l29-12" stroke="#aacbe9" stroke-linecap="round" stroke-width="5"/><path d="m4 24 15 13" stroke="#f4b35e" stroke-linecap="round" stroke-width="6"/></g>
        <g transform="translate(232 81)"><path d="M0 78c24-35 57-39 91-14l29 47H-9Z" fill="#f6b36e"/><circle cx="53" cy="37" r="27" fill="#ffd8ae"/><path d="M27 37c3-28 39-43 59-17-10-4-19-3-27 4-7 6-14 10-32 13Z" fill="#6a79a8"/><circle cx="43" cy="41" r="3" fill="#31405e"/><circle cx="63" cy="41" r="3" fill="#31405e"/><path d="M48 51q7 7 14 0" fill="none" stroke="#de8a74" stroke-linecap="round" stroke-width="3"/><path d="m14 88 36-17 37 18-36 20Z" fill="#79bce8"/><path d="m51 91 35-15 31 20-35 17Z" fill="#5f75db"/><path d="M32 92 6 114M86 93l19 22" fill="none" stroke="#41577d" stroke-linecap="round" stroke-width="8"/></g>
        <g transform="translate(380 105)"><circle cx="44" cy="42" r="35" fill="#fbffff" stroke="#7bd5c1" stroke-width="6" filter="url(#atmo-shadow)"/><circle cx="33" cy="39" r="4" fill="#4a6fd1"/><circle cx="55" cy="39" r="4" fill="#4a6fd1"/><path d="M31 53q13 10 26 0" fill="none" stroke="#70cdb6" stroke-linecap="round" stroke-width="4"/><path d="M44 5V-8M37-10h14" fill="none" stroke="#6f91e5" stroke-linecap="round" stroke-width="5"/><path d="M10 78 0 91M78 78l12 13" fill="none" stroke="#6f91e5" stroke-linecap="round" stroke-width="8"/><circle cx="44" cy="-9" r="5" fill="#f4c45d"/></g>
        <g fill="none" stroke="#6d8fe0" stroke-linecap="round" stroke-width="3" opacity=".66"><path d="M181 148c32-27 54-33 82-19 25 12 36-8 58-18"/><path d="M463 145c20-20 34-18 53-8 15 8 25-2 37-13"/></g>
        <g fill="#fff" stroke="#77a6e7" stroke-width="3"><circle cx="181" cy="148" r="7"/><circle cx="263" cy="129" r="7"/><circle cx="321" cy="111" r="7"/><circle cx="463" cy="145" r="7"/><circle cx="516" cy="137" r="7"/><circle cx="553" cy="124" r="7"/></g>
      </g>

      <g v-else-if="variant === 'empty'">
        <path d="M113 227c39-39 91-58 146-42 35 10 75 11 116-2 70-23 133-1 153 44H113Z" fill="#e3f7ed"/>
        <g transform="translate(208 50)"><path d="M0 28c29-15 61-15 91 0v100H0Z" fill="#fff" stroke="#a7c8e8" stroke-width="4"/><path d="M8 39c26-11 48-11 76 0v70c-25-10-50-10-76 0Z" fill="#edf8ff"/><path d="m26 74 13 14 27-31" fill="none" stroke="#65c9ad" stroke-linecap="round" stroke-linejoin="round" stroke-width="7"/></g>
        <g transform="translate(344 72)"><circle cx="47" cy="46" r="35" fill="#fff" stroke="#7bd5c1" stroke-width="6"/><circle cx="36" cy="42" r="4" fill="#4a6fd1"/><circle cx="58" cy="42" r="4" fill="#4a6fd1"/><path d="M34 56q13 10 26 0" fill="none" stroke="#70cdb6" stroke-linecap="round" stroke-width="4"/><path d="M47 10V-4" stroke="#6f91e5" stroke-linecap="round" stroke-width="5"/><circle cx="47" cy="-8" r="5" fill="#f4c45d"/></g>
        <g fill="#f4c45d"><path d="m460 42 5 12 13 1-10 8 3 13-11-7-11 7 3-13-10-8 13-1Z"/><path d="m157 61 4 9 10 1-8 6 2 10-8-5-8 5 2-10-8-6 10-1Z"/></g>
      </g>

      <g v-else-if="variant === 'path'">
        <path d="M49 226h544" stroke="#d0e8df" stroke-linecap="round" stroke-width="8"/>
        <path d="M88 205c60-65 93-12 138-52 46-40 67-76 117-45 49 31 54-13 94-20 41-7 60 20 112-22" fill="none" stroke="#6b8fe4" stroke-linecap="round" stroke-width="7"/>
        <g fill="#fff" stroke="#6b8fe4" stroke-width="4"><circle cx="88" cy="205" r="12"/><circle cx="226" cy="153" r="12"/><circle cx="343" cy="108" r="12"/><circle cx="437" cy="88" r="12"/><circle cx="549" cy="66" r="12"/></g>
        <g fill="#72cdb4"><path d="m72 176 8 16 18 2-13 12 4 18-17-9-17 9 4-18-13-12 18-2Z"/><path d="m329 47 6 13 15 2-11 10 3 15-13-7-13 7 3-15-11-10 15-2Z"/></g>
        <g transform="translate(279 175)"><path d="m0 43 45-26 45 26-45 25Z" fill="#f6b36e"/><path d="M0 43v18l45 25 45-25V43L45 68Z" fill="#e79a62"/><path d="m45 68 45-25v18L45 86Z" fill="#d98665"/><path d="m17 42 28-16 28 16-28 16Z" fill="#fff4d8"/></g>
      </g>

      <g v-else>
        <circle cx="58" cy="62" r="38" fill="#e1f7ef"/><circle cx="588" cy="205" r="49" fill="#eaf3ff"/>
        <g transform="translate(264 77)"><circle cx="55" cy="51" r="42" fill="#fff" stroke="#7bd5c1" stroke-width="6"/><circle cx="42" cy="48" r="5" fill="#4a6fd1"/><circle cx="68" cy="48" r="5" fill="#4a6fd1"/><path d="M40 65q15 12 30 0" fill="none" stroke="#70cdb6" stroke-linecap="round" stroke-width="5"/><path d="M55 8V-9" stroke="#6f91e5" stroke-linecap="round" stroke-width="6"/><circle cx="55" cy="-14" r="6" fill="#f4c45d"/></g>
        <g fill="#fff" stroke="#a7c8e8" stroke-width="4"><rect x="72" y="137" width="89" height="62" rx="12" transform="rotate(-10 72 137)"/><rect x="473" y="68" width="91" height="63" rx="12" transform="rotate(11 473 68)"/></g>
        <g fill="none" stroke="#70cdb6" stroke-linecap="round" stroke-width="5"><path d="m95 174 12 11 25-28"/><path d="m495 105 13 12 26-29"/></g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.learning-atmosphere { width:100%; pointer-events:none; user-select:none; }.learning-atmosphere svg { display:block; width:100%; height:auto; overflow:visible; }.is-hero { max-width:560px; min-width:320px; }.is-empty { max-width:430px; margin:0 auto; }.is-path { max-width:620px; }.is-side { max-width:260px; }
.atmo-float { transform-box:fill-box; transform-origin:center; animation:atmo-drift 5s ease-in-out infinite alternate; }.atmo-float:nth-of-type(2) { animation-delay:-2.2s; }.atmo-stars { animation:atmo-twinkle 3s ease-in-out infinite alternate; }
@keyframes atmo-drift { from { transform:translateY(0); } to { transform:translateY(-7px); } } @keyframes atmo-twinkle { from { opacity:.45; } to { opacity:1; } }
@media (prefers-reduced-motion:reduce) { .atmo-float,.atmo-stars { animation:none; } }
</style>
