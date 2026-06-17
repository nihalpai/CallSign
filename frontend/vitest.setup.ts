import "@testing-library/jest-dom/vitest";

// jsdom does not implement scrollIntoView — stub it so components that call it don't throw.
if (typeof window !== "undefined") {
  window.HTMLElement.prototype.scrollIntoView = function () {};
}
