const fs = require('fs');
const path = require('path');

const srcDir = path.join(__dirname, 'frontend');
const outDir = path.join(__dirname, 'build');

console.log('Starting build process...');

// Clean and recreate build directory
if (fs.existsSync(outDir)) {
    console.log(`Cleaning existing build folder: ${outDir}`);
    fs.rmSync(outDir, { recursive: true, force: true });
}
fs.mkdirSync(outDir, { recursive: true });

// Copy index.html to the root of build directory
const indexSrc = path.join(srcDir, 'index.html');
const indexOut = path.join(outDir, 'index.html');
if (fs.existsSync(indexSrc)) {
    fs.copyFileSync(indexSrc, indexOut);
    console.log('Copied index.html to build root');
} else {
    console.error('Error: index.html not found in frontend directory!');
    process.exit(1);
}

// Create build/static directory
const staticDir = path.join(outDir, 'static');
fs.mkdirSync(staticDir, { recursive: true });

// Copy app.js and styles.css to build/static
const appJsSrc = path.join(srcDir, 'app.js');
const appJsOut = path.join(staticDir, 'app.js');
if (fs.existsSync(appJsSrc)) {
    fs.copyFileSync(appJsSrc, appJsOut);
    console.log('Copied app.js to build/static/');
} else {
    console.warn('Warning: app.js not found in frontend directory');
}

const stylesCssSrc = path.join(srcDir, 'styles.css');
const stylesCssOut = path.join(staticDir, 'styles.css');
if (fs.existsSync(stylesCssSrc)) {
    fs.copyFileSync(stylesCssSrc, stylesCssOut);
    console.log('Copied styles.css to build/static/');
} else {
    console.warn('Warning: styles.css not found in frontend directory');
}

// Copy audio directory if it exists
const srcAudio = path.join(srcDir, 'audio');
const outAudio = path.join(staticDir, 'audio');
if (fs.existsSync(srcAudio)) {
    copyFolderSync(srcAudio, outAudio);
    console.log('Copied audio assets to build/static/audio/');
}

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

console.log('Build completed successfully!');
