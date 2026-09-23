import { defineConfig } from 'vite'
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const outputRoot = resolve(process.cwd(), 'src/mshub/native/graph')

// Vite treats qrc:/// as an unknown external protocol and removes the script
// from the production HTML.  The native page needs Qt's WebChannel bootstrap
// before graph.js runs, so restore that one runtime-owned script after the
// bundle is written.  It is deliberately not copied into the package: Qt
// provides it from its own resource system.
const qtWebChannelPlugin = {
  name: 'mshub-qt-webchannel-bootstrap',
  closeBundle() {
    const htmlPath = resolve(outputRoot, 'index.html')
    let html = readFileSync(htmlPath, 'utf8')
    if (!html.includes('qrc:///qtwebchannel/qwebchannel.js')) {
      html = html.replace('</head>', '    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>\n  </head>')
      writeFileSync(htmlPath, html, 'utf8')
    }
  },
}

export default defineConfig({
  root: resolve(process.cwd(), 'web/native-graph'),
  base: './',
  plugins: [qtWebChannelPlugin],
  build: {
    outDir: outputRoot,
    emptyOutDir: true,
    rollupOptions: { input: resolve(process.cwd(), 'web/native-graph/index.html') },
  },
})
