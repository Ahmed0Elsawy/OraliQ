import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";

/**
 * Seamless Centerpiece Face-Mesh Video:
 * - Uses the background-unified 1080x1920 biometric animation (/media/hero-face-mesh.mp4)
 *   whose background is unified to #0E0804 and feathered with a multi-stop radial mask
 *   so the character looks like an integral piece of the Hero box itself.
 * - Explicitly forces muted inline playback on mount, media ready, and first touch
 *   so iOS Safari and Android Chrome always play the animation.
 */
export function FaceScan({ priority = false, className }: { tone?: "light" | "dark"; priority?: boolean; className?: string }) {
    const videoRef = useRef<HTMLVideoElement>(null);

    useEffect(() => {
        const v = videoRef.current;
        if (!v) return;
        v.defaultMuted = true;
        v.muted = true;
        v.playsInline = true;

        const tryPlay = () => {
            if (!v) return;
            v.defaultMuted = true;
            v.muted = true;
            if (v.paused) {
                v.play().catch(() => {});
            }
        };

        tryPlay();
        v.addEventListener("loadedmetadata", tryPlay);
        v.addEventListener("loadeddata", tryPlay);
        v.addEventListener("canplay", tryPlay);
        window.addEventListener("touchstart", tryPlay, { once: true, passive: true });
        window.addEventListener("scroll", tryPlay, { once: true, passive: true });
        document.addEventListener("visibilitychange", tryPlay);

        return () => {
            v.removeEventListener("loadedmetadata", tryPlay);
            v.removeEventListener("loadeddata", tryPlay);
            v.removeEventListener("canplay", tryPlay);
            window.removeEventListener("touchstart", tryPlay);
            window.removeEventListener("scroll", tryPlay);
            document.removeEventListener("visibilitychange", tryPlay);
        };
    }, []);

    const maskStyle: React.CSSProperties = {
        WebkitMaskImage:
            "radial-gradient(ellipse 44% 58% at 50% 47%, #000 50%, rgba(0,0,0,0.72) 67%, rgba(0,0,0,0.2) 83%, transparent 95%)",
        maskImage:
            "radial-gradient(ellipse 44% 58% at 50% 47%, #000 50%, rgba(0,0,0,0.72) 67%, rgba(0,0,0,0.2) 83%, transparent 95%)",
    };

    return (
        <div className={cn("relative select-none pointer-events-none flex items-end justify-center", className)}>
            <video
                ref={videoRef}
                src="/media/hero-face-mesh.mp4"
                poster="/media/hero-face-mesh-poster.webp"
                autoPlay
                loop
                muted
                playsInline
                preload={priority ? "auto" : "metadata"}
                style={maskStyle}
                className="block h-full w-full object-contain object-bottom"
            />
        </div>
    );
}
