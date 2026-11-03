import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type ThemePref = "system" | "light" | "dark";

type ThemeContextValue = {
    pref: ThemePref;
    resolved: "light" | "dark";
    setPref: (pref: ThemePref) => void;
    toggle: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);
const STORAGE_KEY = "oraliq_theme";

function readPref(): ThemePref {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        return saved === "light" || saved === "dark" ? saved : "system";
    } catch {
        return "system";
    }
}

function systemTheme(): "light" | "dark" {
    // No window while the home page is rendered at build time; it renders light
    if (typeof window === "undefined") return "light";
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
    const [pref, setPrefState] = useState<ThemePref>(readPref);
    const [system, setSystem] = useState<"light" | "dark">(systemTheme);

    useEffect(() => {
        const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
        if (!mq) return;
        const onChange = () => setSystem(mq.matches ? "dark" : "light");
        mq.addEventListener("change", onChange);
        return () => mq.removeEventListener("change", onChange);
    }, []);

    useEffect(() => {
        const root = document.documentElement;
        if (pref === "system") delete root.dataset.theme;
        else root.dataset.theme = pref;
    }, [pref]);

    const value = useMemo<ThemeContextValue>(() => {
        const resolved = pref === "system" ? system : pref;
        const setPref = (next: ThemePref) => {
            setPrefState(next);
            try {
                if (next === "system") localStorage.removeItem(STORAGE_KEY);
                else localStorage.setItem(STORAGE_KEY, next);
            } catch { /* storage unavailable — theme still applies for this session */ }
        };
        return { pref, resolved, setPref, toggle: () => setPref(resolved === "dark" ? "light" : "dark") };
    }, [pref, system]);

    return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
    const ctx = useContext(ThemeContext);
    if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
    return ctx;
}
