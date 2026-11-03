import React from "react";
import { I18nProvider } from "./i18n";
import { ThemeProvider } from "./lib/theme";
import { ToastProvider } from "./components/ui/toast";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ServerStatus } from "./components/ServerStatus";
import { BrandSprite } from "./components/Logo";

/** Everything around the router; shared by the browser entry and the build-time render of the home page. */
export function AppProviders({ children }: { children: React.ReactNode }) {
    return (
        <React.StrictMode>
            <ErrorBoundary>
                <ThemeProvider>
                    <I18nProvider>
                        <ToastProvider>
                            <BrandSprite />
                            <ServerStatus />
                            {children}
                        </ToastProvider>
                    </I18nProvider>
                </ThemeProvider>
            </ErrorBoundary>
        </React.StrictMode>
    );
}
