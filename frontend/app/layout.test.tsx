/// <reference types="vitest/globals" />
import { readFileSync } from "fs";
import { resolve } from "path";

// Browser extensions (e.g. Grammarly) inject attributes onto <body> before React
// hydrates, causing a mismatch. suppressHydrationWarning on <body> silences it.
// This test ensures that prop is never accidentally removed.
test("RootLayout body has suppressHydrationWarning", () => {
  const src = readFileSync(resolve(__dirname, "layout.tsx"), "utf-8");
  expect(src).toContain("suppressHydrationWarning");
});
