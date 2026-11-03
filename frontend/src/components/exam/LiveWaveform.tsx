import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";

interface LiveWaveformProps {
    stream: MediaStream | null;
    active: boolean;
    className?: string;
    label: string;
}

/**
 * Scrolling bar waveform of the microphone level — tells the student "we hear you"
 * without any numbers. Read-only tap on the stream; recording is untouched.
 */
export function LiveWaveform({ stream, active, className, label }: LiveWaveformProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || !stream || stream.getAudioTracks().length === 0) return;

        const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        const ctx = new AudioCtx();
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);
        const data = new Uint8Array(analyser.fftSize);

        const BARS = 56;
        const levels: number[] = Array(BARS).fill(0);
        const css = getComputedStyle(document.documentElement);
        const color = css.getPropertyValue("--pen").trim() || "#2345B0";
        const idle = css.getPropertyValue("--rule-strong").trim() || "#C3CDDC";
        const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

        let raf = 0;
        let last = 0;
        const draw = (t: number) => {
            raf = requestAnimationFrame(draw);
            if (t - last < (reduce ? 200 : 60)) return;
            last = t;

            analyser.getByteTimeDomainData(data);
            let sum = 0;
            for (let i = 0; i < data.length; i++) {
                const v = (data[i] - 128) / 128;
                sum += v * v;
            }
            const rms = Math.sqrt(sum / data.length);
            levels.push(active ? Math.min(1, rms * 4.5) : 0);
            levels.shift();

            const dpr = window.devicePixelRatio || 1;
            const w = canvas.clientWidth;
            const h = canvas.clientHeight;
            if (canvas.width !== w * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
            const g = canvas.getContext("2d");
            if (!g) return;
            g.setTransform(dpr, 0, 0, dpr, 0, 0);
            g.clearRect(0, 0, w, h);
            const step = w / BARS;
            const barW = Math.max(2, step * 0.5);
            levels.forEach((lv, i) => {
                const bh = Math.max(3, lv * h);
                g.fillStyle = active && lv > 0.02 ? color : idle;
                const x = i * step + (step - barW) / 2;
                g.beginPath();
                g.roundRect(x, (h - bh) / 2, barW, bh, barW / 2);
                g.fill();
            });
        };
        raf = requestAnimationFrame(draw);

        return () => {
            cancelAnimationFrame(raf);
            source.disconnect();
            ctx.close().catch(() => {});
        };
    }, [stream, active]);

    return <canvas ref={canvasRef} role="img" aria-label={label} className={cn("h-12 w-full", className)} />;
}
