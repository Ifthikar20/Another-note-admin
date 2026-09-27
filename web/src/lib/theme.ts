/** Light, dark or the system's choice, remembered in localStorage (public/theme-init.js applies it before paint). */
import { useCallback, useEffect, useState } from "react";

export type ThemeChoice = "light" | "dark" | "system";
const KEY = "admin.theme";

function stored(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* blocked storage */
  }
  return "system";
}

function systemDark(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

function apply(choice: ThemeChoice) {
  const dark = choice === "dark" || (choice === "system" && systemDark());
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(stored);
  useEffect(() => {
    apply(choice);
    if (choice !== "system") return;
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    media?.addEventListener?.("change", onChange);
    return () => media?.removeEventListener?.("change", onChange);
  }, [choice]);
  const set = useCallback((next: ThemeChoice) => {
    setChoice(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* blocked storage: the choice lasts this page only */
    }
  }, []);
  const isDark = choice === "dark" || (choice === "system" && systemDark());
  return { choice, set, isDark, toggle: () => set(isDark ? "light" : "dark") };
}
