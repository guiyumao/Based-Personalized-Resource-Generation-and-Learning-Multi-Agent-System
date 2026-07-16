const sharp = require('sharp');
const path = require('path');

async function createGradients() {
  const gradients = [
    { name: 'cover-bg', color1: '#0A1628', color2: '#1E3A5F', angle: 135 },
    { name: 'header-bar', color1: '#0F2040', color2: '#1E5AAB', angle: 90 },
    { name: 'accent-strip', color1: '#1E5AAB', color2: '#3B82F6', angle: 0 },
    { name: 'section-bg', color1: '#F0F4F8', color2: '#E2E8F0', angle: 180 },
    { name: 'dark-footer', color1: '#0A1628', color2: '#162D50', angle: 90 },
    { name: 'feature-card', color1: '#1E5AAB', color2: '#0F2040', angle: 135 },
    { name: 'tech-bar', color1: '#2D3748', color2: '#1A202C', angle: 90 },
  ];

  for (const g of gradients) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="${g.angle === 135 ? '100%' : g.angle === 90 ? '0%' : '100%'}" y2="${g.angle === 135 ? '100%' : g.angle === 90 ? '100%' : '0%'}">
          <stop offset="0%" style="stop-color:${g.color1}"/>
          <stop offset="100%" style="stop-color:${g.color2}"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#g)"/>
    </svg>`;

    await sharp(Buffer.from(svg)).png().toFile(path.join(__dirname, 'gradients', `${g.name}.png`));
    console.log(`Created: ${g.name}.png`);
  }
}

createGradients().catch(console.error);
