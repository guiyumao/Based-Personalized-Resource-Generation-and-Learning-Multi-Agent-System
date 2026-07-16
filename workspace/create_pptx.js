const pptxgen = require('pptxgenjs');
const html2pptx = require('C:/Users/wdx/.claude/skills/pptx/scripts/html2pptx');
const path = require('path');

const slidesDir = path.join(__dirname, 'slides');

async function createPresentation() {
    const pptx = new pptxgen();
    pptx.layout = 'LAYOUT_16x9';
    pptx.author = 'Multi-Agent Learning Platform';
    pptx.title = '基于大模型的个性化资源生成与学习多智能体系统';
    pptx.subject = '项目功能说明';

    const slideFiles = [];
    for (let i = 1; i <= 17; i++) {
        slideFiles.push(`slide${String(i).padStart(2, '0')}.html`);
    }

    for (const file of slideFiles) {
        const filePath = path.join(slidesDir, file);
        console.log(`Processing: ${file}`);
        try {
            await html2pptx(filePath, pptx);
        } catch (err) {
            console.error(`Error processing ${file}: ${err.message}`);
        }
    }

    const outputPath = path.join(__dirname, '..', '个性化资源生成与学习多智能体系统.pptx');
    await pptx.writeFile({ fileName: outputPath });
    console.log(`Presentation saved to: ${outputPath}`);
}

createPresentation().catch(console.error);
