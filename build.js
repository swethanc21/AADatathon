const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, 'frontend');

console.log('Starting build process...');

function copyFolderSync(from, to) {
    fs.mkdirSync(to, { recursive: true });
    fs.readdirSync(from).forEach(element => {
        const fromPath = path.join(from, element);
        const toPath = path.join(to, element);
        if (fs.lstatSync(fromPath).isDirectory()) {
            copyFolderSync(fromPath, toPath);
        } else {
            fs.copyFileSync(fromPath, toPath);
        }
    });
}

function buildToFolder(folderName) {
    const outDir = path.join(__dirname, folderName);
    console.log(`Building to folder: ${outDir}`);

    // Clean and recreate directory
    if (fs.existsSync(outDir)) {
        console.log(`Cleaning existing folder: ${outDir}`);
        fs.rmSync(outDir, { recursive: true, force: true });
    }
    fs.mkdirSync(outDir, { recursive: true });

    // Copy index.html to root of folder
    const indexSrc = path.join(srcDir, 'index.html');
    const indexOut = path.join(outDir, 'index.html');
    if (fs.existsSync(indexSrc)) {
        fs.copyFileSync(indexSrc, indexOut);
        console.log(`Copied index.html to ${folderName} root`);
    } else {
        console.error('Error: index.html not found in frontend directory!');
        process.exit(1);
    }

    // Create static directory
    const staticDir = path.join(outDir, 'static');
    fs.mkdirSync(staticDir, { recursive: true });

    // Copy app.js and styles.css
    const appJsSrc = path.join(srcDir, 'app.js');
    const appJsOut = path.join(staticDir, 'app.js');
    if (fs.existsSync(appJsSrc)) {
        fs.copyFileSync(appJsSrc, appJsOut);
        console.log(`Copied app.js to ${folderName}/static/`);
    } else {
        console.warn(`Warning: app.js not found`);
    }

    const stylesCssSrc = path.join(srcDir, 'styles.css');
    const stylesCssOut = path.join(staticDir, 'styles.css');
    if (fs.existsSync(stylesCssSrc)) {
        fs.copyFileSync(stylesCssSrc, stylesCssOut);
        console.log(`Copied styles.css to ${folderName}/static/`);
    } else {
        console.warn(`Warning: styles.css not found`);
    }

    // Copy audio directory if it exists
    const srcAudio = path.join(srcDir, 'audio');
    const outAudio = path.join(staticDir, 'audio');
    if (fs.existsSync(srcAudio)) {
        copyFolderSync(srcAudio, outAudio);
        console.log(`Copied audio assets to ${folderName}/static/audio/`);
    }
}

// Build to both build and dist to guarantee compatibility with any Zoho configuration
buildToFolder('build');
buildToFolder('dist');

console.log('Build completed successfully!');
