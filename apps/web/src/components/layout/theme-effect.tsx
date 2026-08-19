/**
 * File purpose: Renders and coordinates the theme effect user-interface feature.
 * Main declarations: ThemeEffect handles theme effect.
 */

"use client";

import { useEffect } from "react";
import { useUiStore } from "@/stores";

export function ThemeEffect() {
  const theme = useUiStore((state) => state.theme);

  useEffect(() => {
    const root = document.documentElement;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const activeTheme = theme === "system" ? (prefersDark ? "dark" : "light") : theme;

    root.dataset.theme = activeTheme;
  }, [theme]);

  return null;
}
