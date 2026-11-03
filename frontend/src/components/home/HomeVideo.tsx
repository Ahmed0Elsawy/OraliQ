import { useRef, useState } from "react";
import { Play, Pause, Volume2, VolumeX, Sparkles, ScanFace, Mic, FileCheck2 } from "lucide-react";
import { useI18n } from "../../i18n";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { Eyebrow, H2, Section } from "./ui";

const VIDEO = { src: "/media/oraliq-demo.mp4", poster: "/media/oraliq-demo-poster.webp" };

/**
 * Section 3 (#video): Introductory Video (الفيديو التعريفي للمنصة)
 * Theme-aware & responsive across Mobile, Tablet, and Desktop.
 */
export function HomeVideo() {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);
    const [playing, setPlaying] = useState(false);
    const [muted, setMuted] = useState(false);

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-video-head]",
                { y: 32, opacity: 0 },
                {
                    y: 0,
                    opacity: 1,
                    duration: 0.7,
                    stagger: 0.1,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-video-head-wrap]", start: "top 82%" },
                },
            );
            gsap.fromTo(
                "[data-video-stage]",
                { y: 56, opacity: 0.35, scale: 0.95 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    ease: "power2.out",
                    scrollTrigger: {
                        trigger: "[data-video-stage]",
                        start: "top 88%",
                        end: "top 38%",
                        scrub: 0.45,
                    },
                },
            );
        });
    }, { scope: root, dependencies: [lang] });

    const togglePlay = () => {
        const v = videoRef.current;
        if (!v) return;
        if (v.paused) {
            void v.play();
            setPlaying(true);
        } else {
            v.pause();
            setPlaying(false);
        }
    };

    const toggleMute = () => {
        const v = videoRef.current;
        if (!v) return;
        v.muted = !v.muted;
        setMuted(v.muted);
    };

    const highlights = [
        {
            num: "01",
            icon: FileCheck2,
            tone: "bg-[#FAF6F0] text-[#1C1410]",
            title: l("إنشاء الكويز الشفوي في ثواني", "Create Oral Quiz in Seconds"),
            desc: l("إضافة الأسئلة والإجابة النموذجية وتحديد الوقت.", "Add questions, model answers, and time limits."),
        },
        {
            num: "02",
            icon: ScanFace,
            tone: "bg-[#EFE7DE] text-[#1C1410]",
            title: l("التحقق من الوجه والعين والصوت", "Face, Eye-Gaze & Voice Check"),
            desc: l("تتبع 478 نقطة حيوية لمنع الغش أثناء الإجابة.", "478-point biometric tracking prevents cheating."),
        },
        {
            num: "03",
            icon: Mic,
            tone: "bg-[#E5DACB] text-[#1C1410]",
            title: l("إجابة الطالب بصوته وتفريغها", "Spoken Answer & Live Transcript"),
            desc: l("تحويل الصوت لنص وتحليل الطلاقة لحظياً.", "Real-time speech-to-text and fluency analysis."),
        },
        {
            num: "04",
            icon: Sparkles,
            tone: "bg-[#FAF6F0] text-[#1C1410]",
            title: l("التصحيح بالمعنى وإصدار التقرير", "Semantic Grading & Final Report"),
            desc: l("الدرجة الكاملة جاهزة للدكتور مع سبب كل درجة.", "Full score ready for the lecturer with AI reasoning."),
        },
    ];

    return (
        <Section id="video" tone="a" className="py-16 sm:py-24 lg:py-32">
            <div ref={root} className="mx-auto max-w-[92rem] px-5 sm:px-10 lg:px-16">
                {/* Section Header */}
                <div data-video-head-wrap className="mx-auto max-w-3xl text-center">
                    <div data-video-head>
                        <Eyebrow className="text-pen">
                            {l("الفيديو التعريفي للمنصة", "Platform Walkthrough Video")}
                        </Eyebrow>
                    </div>
                    <h2 data-video-head className={`${H2} mt-3 text-ink`}>
                        {l(
                            "شوف إزاي الكويز الشفوي بيشتغل من البداية للنهاية.",
                            "See How the Online Oral Quiz Works From Start to Finish.",
                        )}
                    </h2>
                    <p data-video-head className="ar-body mt-4 sm:mt-5 text-base sm:text-xl font-medium leading-[1.85] text-ink-2">
                        {l(
                            "في دقيقة واحدة، شوف رحلة الامتحان الشفوي كاملة: من لحظة كتابة الدكتور للسؤال، لدخول الطالب ومطابقة بصمة الوجه والصوت، لحد ما الـ 3 موديلات تطلع النتيجة متصححة بالمعنى.",
                            "In one minute, watch the entire oral exam flow: from creating the question, to student biometric check-in, to the 3 AI models delivering a semantically graded score.",
                        )}
                    </p>
                </div>

                {/* Studio Showcase Frame */}
                <div
                    data-video-stage
                    style={{
                        background:
                            "radial-gradient(at 35% 40%, rgba(111, 78, 55, 0.45), transparent 65%), radial-gradient(at 80% 75%, rgba(227, 164, 88, 0.16), transparent 55%), #1D140F",
                    }}
                    className="mx-auto mt-8 sm:mt-12 max-w-[80rem] overflow-hidden rounded-[22px] sm:rounded-[28px] border border-rule p-3 shadow-float sm:p-6"
                >
                    {/* Studio Window Top Bar */}
                    <div className="mb-3.5 flex flex-wrap items-center justify-between gap-2.5 rounded-2xl border border-[#FAF6F0]/12 bg-[#140E0A]/80 px-3.5 py-2.5 sm:px-4 sm:py-3 text-[#FAF6F0] backdrop-blur-md">
                        <div className="flex items-center gap-2">
                            <span className="size-2.5 sm:size-3 rounded-full bg-[#E3A458]" aria-hidden />
                            <span className="size-2.5 sm:size-3 rounded-full bg-[#EFE7DE]" aria-hidden />
                            <span className="size-2.5 sm:size-3 rounded-full bg-[#6F4E37]" aria-hidden />
                            <span className="ms-1.5 text-xs font-bold text-[#FAF6F0]/85">
                                OralIQ Studio
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                type="button"
                                onClick={toggleMute}
                                className="inline-flex items-center gap-1.5 rounded-full border border-[#FAF6F0]/15 bg-[#FAF6F0]/10 px-3 py-1.5 text-xs font-bold text-[#FAF6F0] hover:bg-[#FAF6F0]/20"
                            >
                                {muted ? <VolumeX className="size-3.5" aria-hidden /> : <Volume2 className="size-3.5" aria-hidden />}
                                <span>{muted ? l("تشغيل الصوت", "Unmute") : l("كتم الصوت", "Mute")}</span>
                            </button>
                            <button
                                type="button"
                                onClick={togglePlay}
                                className="inline-flex items-center gap-1.5 rounded-full bg-[#E3A458] px-3.5 sm:px-4 py-1.5 text-xs font-bold text-[#18110D] hover:bg-[#eab471]"
                            >
                                {playing ? <Pause className="size-3.5 fill-current" aria-hidden /> : <Play className="size-3.5 fill-current" aria-hidden />}
                                <span>{playing ? l("إيقاف مؤقت", "Pause") : l("تشغيل الفيديو", "Play Video")}</span>
                            </button>
                        </div>
                    </div>

                    {/* Video Viewport */}
                    <div className="relative aspect-video w-full overflow-hidden rounded-[16px] sm:rounded-[20px] border border-[#FAF6F0]/15 bg-[#120D09]">
                        <video
                            ref={videoRef}
                            src={VIDEO.src}
                            poster={VIDEO.poster}
                            controls={playing}
                            playsInline
                            onPlay={() => setPlaying(true)}
                            onPause={() => setPlaying(false)}
                            onEnded={() => setPlaying(false)}
                            className="size-full object-cover"
                        />

                        {!playing && (
                            <button
                                type="button"
                                onClick={togglePlay}
                                aria-label={l("تشغيل الفيديو التعريفي", "Play walkthrough video")}
                                className="group absolute inset-0 flex flex-col items-center justify-center gap-3 sm:gap-4 bg-[#18110D]/45 p-4 backdrop-blur-[2px] transition-colors hover:bg-[#18110D]/30"
                            >
                                <span className="flex size-16 sm:size-24 items-center justify-center rounded-full border border-[#FAF6F0]/30 bg-[#6F4E37] text-[#FAF6F0] shadow-[0_18px_45px_rgba(0,0,0,0.45)] transition-transform duration-300 group-hover:scale-105">
                                    <Play className="size-7 sm:size-9 fill-current" aria-hidden />
                                </span>
                                <span className="rounded-full border border-[#FAF6F0]/20 bg-[#FAF6F0] px-4 py-1.5 sm:px-5 sm:py-2 text-xs sm:text-sm font-bold text-[#1C1410] shadow-lg text-center">
                                    {l("اضغط لمشاهدة الفيديو التعريفي (دقيقة واحدة)", "Click to watch the 1-minute walkthrough")}
                                </span>
                            </button>
                        )}
                    </div>

                    {/* 4 Chapter / Feature Cards Under the Video */}
                    <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        {highlights.map((h) => (
                            <div
                                key={h.title}
                                className={`rounded-[18px] sm:rounded-[20px] p-4 sm:p-5 ${h.tone}`}
                            >
                                <div className="flex items-center justify-between gap-2">
                                    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#6F4E37] text-[#FAF6F0]">
                                        <h.icon className="size-4" aria-hidden />
                                    </span>
                                    <span className="wb-num text-sm font-extrabold text-[#6F4E37]/60">{h.num}</span>
                                </div>
                                <h3 className="ar-heading mt-3 text-base font-bold text-[#1C1410]">{h.title}</h3>
                                <p className="ar-body mt-1 text-xs font-medium leading-relaxed text-[#1C1410]/80">
                                    {h.desc}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </Section>
    );
}
