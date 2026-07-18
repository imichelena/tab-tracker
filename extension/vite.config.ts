import { defineConfig, type LibraryFormats } from "vite";

// Shopify POS UI extensions use a sandboxed iframe.
// The extension is built as a library consumed by Shopify's extension runtime.
// No HTML shell is needed — vite outputs pure JS consumed by the POS host.
export default defineConfig({
  build: {
    lib: {
      entry: {
        index: "./src/index.tsx",
        Modal: "./src/Modal.tsx",
      },
      formats: ["es"] as LibraryFormats[],
      fileName: (_format: string, entryName: string): string => `${entryName}.js`,
    },
    rollupOptions: {
      external: [
        // These are provided by the Shopify POS extension runtime — not bundled
        "@shopify/ui-extensions",
        "@shopify/ui-extensions/point-of-sale",
        "@shopify/ui-extensions-react",
        "@shopify/ui-extensions-react/point-of-sale",
        "react",
        "react-dom",
      ],
    },
    outDir: "dist",
    sourcemap: true,
    emptyOutDir: true,
  },
});
