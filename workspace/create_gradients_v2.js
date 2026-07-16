const sharp = require('sharp');
const path = require('path');

const outDir = path.join(__dirname, 'gradients');
const fs = require('fs');
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

async function createGradients() {
  // Modern, beautiful gradient assets
  const assets = [
    // Dark blue tech gradients
    { name: 'cover-bg', svg: `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#0B1120"/><stop offset="50%" style="stop-color:#1A2744"/><stop offset="100%" style="stop-color:#0F2847"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>` },
    { name: 'header-bar', svg: `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" style="stop-color:#0F1A3A"/><stop offset="60%" style="stop-color:#15294A"/><stop offset="100%" style="stop-color:#1E4D8C"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>` },
    { name: 'accent-blue', svg: `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#2563EB"/><stop offset="100%" style="stop-color:#3B82F6"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>` },
    { name: 'accent-teal', svg: `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" style="stop-color:#0D9488"/><stop offset="100%" style="stop-color:#14B8A6"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>` },
    { name: 'accent-purple', svg: `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#6D28D9"/><stop offset="100%" style="stop-color:#7C3AED"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>` },
    { name: 'accent-amber', svg: `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" style="stop-color:#D97706"/><stop offset="100%" style="stop-color:#F59E0B"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>` },
    // Light section backgrounds
    { name: 'light-gray', svg: `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810"><defs><linearGradient id="g" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" style="stop-color:#F8FAFC"/><stop offset="100%" style="stop-color:#F1F5F9"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>` },
    { name: 'subtle-blue', svg: `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="810"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#EFF6FF"/><stop offset="100%" style="stop-color:#DBEAFE"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/></svg>` },
  ];

  for (const asset of assets) {
    await sharp(Buffer.from(asset.svg)).png().toFile(path.join(outDir, `${asset.name}.png`));
    console.log(`Created: ${asset.name}.png`);
  }
  console.log('Done.');
}

createGradients().catch(console.error);
