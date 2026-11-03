import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import { onServerSlow } from "../lib/api";
import { useI18n } from "../i18n";

/** Thin top notice while the API is slow to answer, and when the device goes offline. */
export function ServerStatus() {
    const { l } = useI18n();
    const [slow, setSlow] = useState(false);
    const [offline, setOffline] = useState(typeof navigator !== "undefined" && navigator.onLine === false);

    useEffect(() => onServerSlow(setSlow), []);
    useEffect(() => {
        const on = () => setOffline(false);
        const off = () => setOffline(true);
        window.addEventListener("online", on);
        window.addEventListener("offline", off);
        return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
    }, []);

    if (!slow && !offline) return null;

    return (
        <div role="status" aria-live="polite" className="fixed inset-x-0 top-0 z-[90] flex justify-center px-4 pt-2 print:hidden">
            <div className="flex items-center gap-2.5 rounded-full bg-ink px-4 py-2 text-sm text-paper shadow-pop animate-[oiq-pop-in_180ms_ease-out]">
                {offline ? (
                    <>
                        <WifiOff className="size-4 text-warn" aria-hidden />
                        {l("مفيش إنترنت. هنكمّل أول ما الاتصال يرجع.", "You're offline. We'll continue once you're back online.")}
                    </>
                ) : (
                    <>
                        <span className="size-3.5 animate-spin rounded-full border-2 border-paper/40 border-t-paper" aria-hidden />
                        {l("السيرفر بيجهز… أول طلب ممكن ياخد لحد دقيقة.", "The server is starting up… the first request can take up to a minute.")}
                    </>
                )}
            </div>
        </div>
    );
}
