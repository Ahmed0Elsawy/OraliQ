import { useState, useRef, useEffect } from "react";
import { Check, Mic, RefreshCw, ScanFace } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import { Alert, Modal } from "./ui/feedback";
import { DrawnCheck } from "./motion";
import { buildFaceEnrollForm } from "../lib/faceBiometrics";
import { isAxiosError } from "axios";
import { getApiErrorMessage } from "../lib/apiErrors";

interface VoiceEnrollmentModalProps {
    isOpen: boolean;
    onClose?: () => void;
    onSuccess: () => void;
    isRequired?: boolean;
}

type Step = "idle" | "recording" | "uploading" | "success" | "error";
type EnrollPhase = "face" | "voice";

const RECORD_SECONDS = 6;

const PHRASES = [
    "أنا أؤكد هويتي الآن من خلال بصمة صوتي لأداء الامتحان بأمانة ومصداقية.",
    "التعليم هو السلاح الأقوى الذي يمكنك استخدامه لتغيير العالم من حولك.",
    "العلم نور والجهل ظلام ومن طلب العلا سهر الليالي واجتهد في طلب المعرفة.",
];

/**
 * Mount the flow only while open: every opening starts from a clean slate,
 * and closing unmounts it — which stops the camera/mic via the unmount cleanup.
 */
export default function VoiceEnrollmentModal(props: VoiceEnrollmentModalProps) {
    return props.isOpen ? <EnrollmentFlow {...props} /> : null;
}

function EnrollmentFlow({
    onClose,
    onSuccess,
    isRequired = false,
}: VoiceEnrollmentModalProps) {
    const [enrollPhase, setEnrollPhase] = useState<EnrollPhase>("face");
    const [step, setStep] = useState<Step>("idle");
    const [phraseIndex, setPhraseIndex] = useState(0);
    const [recordingTime, setRecordingTime] = useState(0);
    const [errorMsg, setErrorMsg] = useState("");
    const [recordedBlobs, setRecordedBlobs] = useState<Blob[]>([]);
    const [faceScanProgress, setFaceScanProgress] = useState(0);
    const [faceScanning, setFaceScanning] = useState(false);
    const [faceModelsLoading, setFaceModelsLoading] = useState(true);
    const [faceModelsReady, setFaceModelsReady] = useState(false);
    const [camAttempt, setCamAttempt] = useState(0);
    const [consent, setConsent] = useState(false);
    const { l } = useI18n();

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const faceVideoRef = useRef<HTMLVideoElement>(null);
    const stoppingRef = useRef(false);

    // ── Cleanup on close / unmount ───────────────────────────────────────────
    const cleanup = () => {
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
        if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
        mediaRecorderRef.current = null;
        chunksRef.current = [];
        stoppingRef.current = false;
    };

    // Stop camera/mic and timers when the flow closes (unmounts).
    useEffect(() => () => cleanup(), []);

    // Face ID runs on the server (InsightFace) — no heavy browser models to preload
    useEffect(() => {
        if (enrollPhase !== "face") return;
        let cancelled = false;
        api.get("/face/status")
            .then(() => {
                if (!cancelled) {
                    setFaceModelsReady(true);
                    setFaceModelsLoading(false);
                }
            })
            .catch(() => {
                // Still allow scan — enroll endpoint will load models lazily
                if (!cancelled) {
                    setFaceModelsReady(true);
                    setFaceModelsLoading(false);
                }
            });
        return () => { cancelled = true; };
    }, [enrollPhase]);

    // Face ID camera
    useEffect(() => {
        if (enrollPhase !== "face") return;

        let cancelled = false;
        (async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: "user", width: 640, height: 480 },
                    audio: false,
                });
                if (cancelled) {
                    stream.getTracks().forEach(t => t.stop());
                    return;
                }
                streamRef.current = stream;
                if (faceVideoRef.current) {
                    faceVideoRef.current.srcObject = stream;
                    await faceVideoRef.current.play().catch(() => {});
                }
            } catch {
                if (!cancelled) {
                    setErrorMsg(l("اسمح للمتصفح باستخدام الكاميرا عشان نقدر نمسح وشك.", "Allow the browser to use your camera so we can scan your face."));
                    setStep("error");
                }
            }
        })();

        return () => { cancelled = true; };
    }, [enrollPhase, camAttempt]);

    const totalPhrases = PHRASES.length;

    const startFaceScan = async () => {
        const video = faceVideoRef.current;
        if (!video) return;
        setErrorMsg("");
        setFaceScanning(true);
        setFaceScanProgress(0);

        const progressTimer = setInterval(() => {
            setFaceScanProgress(p => Math.min(p + 12, 95));
        }, 350);

        try {
            await api.get("/users/me");

            const fd = await buildFaceEnrollForm(video, 5, 380);
            await api.post("/face/enroll", fd, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 120_000,
            });
            clearInterval(progressTimer);
            setFaceScanProgress(100);
            streamRef.current?.getTracks().forEach(t => t.stop());
            streamRef.current = null;
            setTimeout(() => {
                setFaceScanning(false);
                setEnrollPhase("voice");
                setStep("idle");
            }, 600);
        } catch (err: any) {
            clearInterval(progressTimer);
            setFaceScanning(false);
            setFaceScanProgress(0);
            // Only a request error is about the server; a face the camera could not read is about light and framing
            const faceFailed = l("ماقدرناش نمسح الوش. اتأكد من الإضاءة وإن وشك كله باين، وجرّب تاني.", "Couldn't scan your face. Check the lighting and that your whole face is in view, then try again.");
            setErrorMsg(isAxiosError(err) ? getApiErrorMessage(err, faceFailed) : faceFailed);
            setStep("error");
        }
    };

    // ── Start recording ──────────────────────────────────────────────────────
    const startRecording = async () => {
        setErrorMsg("");
        setRecordingTime(0);
        chunksRef.current = [];
        stoppingRef.current = false;

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;

            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : "audio/webm";
            const recorder = new MediaRecorder(stream, { mimeType });
            mediaRecorderRef.current = recorder;

            recorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunksRef.current.push(e.data);
            };

            recorder.onstop = () => {
                streamRef.current?.getTracks().forEach(t => t.stop());
                streamRef.current = null;
                const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
                onPhraseRecorded(audioBlob);
            };

            recorder.start(100);
            setStep("recording");

            let seconds = 0;
            timerRef.current = setInterval(() => {
                seconds += 1;
                setRecordingTime(seconds);
                if (seconds >= RECORD_SECONDS) {
                    stopRecording();
                }
            }, 1000);

        } catch (err) {
            console.error("Mic access error:", err);
            setErrorMsg(l("مقدرناش نوصل للميكروفون. اسمح للمتصفح يستخدمه وجرّب تاني.", "We couldn't reach your microphone. Allow the browser to use it and try again."));
            setStep("error");
        }
    };

    // ── Stop recording ───────────────────────────────────────────────────────
    const stopRecording = () => {
        if (stoppingRef.current) return;
        stoppingRef.current = true;
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
        const rec = mediaRecorderRef.current;
        if (rec && rec.state === "recording") {
            rec.stop();
        } else {
            stoppingRef.current = false;
        }
    };

    // ── Handle each phrase recording completion ──────────────────────────────
    const onPhraseRecorded = (blob: Blob) => {
        if (blob.size < 1000) {
            setErrorMsg(l("التسجيل قصير شوية. اقرا الجملة بصوت واضح وجرّب تاني.", "That recording was a little short. Read the sentence clearly and try again."));
            setStep("error");
            return;
        }

        const newBlobs = [...recordedBlobs, blob];
        setRecordedBlobs(newBlobs);

        if (newBlobs.length < totalPhrases) {
            // More phrases to record
            setPhraseIndex(newBlobs.length);
            setStep("idle");
            setRecordingTime(0);
            stoppingRef.current = false;
        } else {
            // All phrases recorded — upload combined
            handleUpload(newBlobs);
        }
    };

    // ── Upload all recordings ────────────────────────────────────────────────
    const handleUpload = async (blobs: Blob[]) => {
        setStep("uploading");
        setErrorMsg("");

        const formData = new FormData();
        blobs.forEach((blob, i) => {
            formData.append("audio_files", blob, `voiceprint_${i}.webm`);
        });

        try {
            const res = await api.post("/voice/enroll-multi", formData, {
                headers: { "Content-Type": "multipart/form-data" },
            });

            if (res.data?.ok) {
                setStep("success");
                setTimeout(() => onSuccess(), 1400);
            } else {
                setErrorMsg(l("صوتك ماتسجلش المرة دي. جرّب تاني.", "Your voice wasn't saved this time. Try again."));
                setStep("error");
            }
        } catch (err: any) {
            console.error("Voice enrollment error:", err);
            setErrorMsg(getApiErrorMessage(err, l("حصلت مشكلة وإحنا بنحفظ صوتك. جرّب تاني.", "Something went wrong saving your voice. Try again.")));
            setStep("error");
        }
    };

    /** Retry from where the student is — never throw away a finished face scan. */
    const retry = () => {
        setErrorMsg("");
        if (enrollPhase === "face") {
            setStep("idle");
            if (!streamRef.current) setCamAttempt((n) => n + 1); // camera was denied/stopped — ask again
            return;
        }
        if (recordedBlobs.length >= totalPhrases) {
            handleUpload(recordedBlobs); // all phrases recorded; only the upload failed
            return;
        }
        stoppingRef.current = false;
        setRecordingTime(0);
        setStep("idle");
    };

    const progress = Math.min((recordingTime / RECORD_SECONDS) * 100, 100);
    const completedCount = recordedBlobs.length;
    const closable = !isRequired && !!onClose && step !== "uploading" && !faceScanning;

    const stages = [
        { key: "face", label: l("الوجه", "Face"), done: enrollPhase === "voice" || step === "success" },
        { key: "voice", label: l("الصوت", "Voice"), done: step === "success" },
    ];

    return (
        <Modal
            open
            onClose={() => { if (closable) onClose?.(); }}
            size="md"
            title={step === "success" ? l("هويتك اتسجلت", "Your identity is registered") : l("تسجيل الوجه والصوت", "Register your face and voice")}
            description={step === "success"
                ? l("هنقارن وشك وصوتك بيهم تلقائياً في كل امتحان.", "We'll compare your face and voice against these in every exam.")
                : l("خطوتين بس، وبيتعملوا مرة واحدة.", "Two quick steps, done once.")}
            footer={closable && step !== "success" ? <Button variant="ghost" onClick={onClose}>{l("بعدين", "Later")}</Button> : undefined}
        >
            {/* Stage indicator */}
            {step !== "success" && (
                <ol className="mb-6 flex items-center gap-3 text-sm">
                    {stages.map((st, i) => {
                        const current = st.key === enrollPhase;
                        return (
                            <li key={st.key} className="flex items-center gap-2" aria-current={current ? "step" : undefined}>
                                {i > 0 && <span className="h-px w-8 bg-rule-strong" aria-hidden />}
                                <span className={cn(
                                    "flex size-7 items-center justify-center rounded-full border font-display text-xs font-semibold",
                                    st.done ? "border-pass bg-pass text-pen-ink" : current ? "border-pen bg-pen-wash text-pen" : "border-rule-strong text-ink-3",
                                )}>
                                    {st.done ? <Check className="size-4" aria-hidden /> : i + 1}
                                </span>
                                <span className={cn(current ? "font-semibold text-ink" : "text-ink-2")}>{st.label}</span>
                            </li>
                        );
                    })}
                </ol>
            )}

            {/* ── Face ── */}
            {enrollPhase === "face" && step !== "success" && (
                <div className="flex flex-col items-center text-center">
                    <div className={cn(
                        "relative aspect-square w-full max-w-48 overflow-hidden sm:max-w-60 rounded-full bg-sheet-2 ring-4 transition-colors",
                        faceScanning ? "ring-pen" : "ring-rule",
                    )}>
                        <video ref={faceVideoRef} muted playsInline className="size-full -scale-x-100 object-cover" />
                        {faceScanning && (
                            <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                                <ScanFace className="size-12 text-white motion-safe:animate-pulse" aria-hidden />
                            </div>
                        )}
                    </div>
                    {faceScanning ? (
                        <div className="mt-5 w-full max-w-60" role="status">
                            <div className="h-1.5 overflow-hidden rounded-full bg-rule">
                                <div className="h-full rounded-full bg-pen transition-[width] duration-300" style={{ width: `${faceScanProgress}%` }} />
                            </div>
                            <p className="mt-2 text-sm text-ink-2">{l("ثبّت راسك… بناخد كام صورة", "Hold still… taking a few photos")}</p>
                        </div>
                    ) : (
                        <p className="mt-5 max-w-sm text-ink-2">
                            {l("بص للكاميرا مباشرة في مكان منوّر، ومن غير نضارة شمس أو كمامة.", "Look straight at the camera in good light, without sunglasses or a mask.")}
                        </p>
                    )}
                </div>
            )}

            {/* ── Voice ── */}
            {enrollPhase === "voice" && step !== "success" && step !== "uploading" && (
                <div>
                    <p className="text-sm text-ink-2">
                        {l(`اقرأ الجملة بصوت عالي وواضح (${phraseIndex + 1} من ${totalPhrases})`, `Read the sentence aloud, clearly (${phraseIndex + 1} of ${totalPhrases})`)}
                    </p>
                    <blockquote
                        className="mt-3 rounded-[var(--radius-control)] border border-rule bg-sheet-2 px-5 py-4 font-display text-xl font-medium leading-[2.4rem]"
                        dir="rtl"
                        style={{ backgroundImage: "repeating-linear-gradient(to bottom, transparent 0, transparent calc(2.4rem - 1px), var(--rule) calc(2.4rem - 1px), var(--rule) 2.4rem)", backgroundPositionY: "1rem" }}
                    >
                        {PHRASES[phraseIndex]}
                    </blockquote>
                    <div className="mt-3 flex gap-1.5" aria-hidden>
                        {PHRASES.map((_, i) => (
                            <span key={i} className={cn("h-1 flex-1 rounded-full", i < completedCount ? "bg-pass" : i === phraseIndex ? "bg-pen" : "bg-rule")} />
                        ))}
                    </div>
                </div>
            )}

            {step === "error" && errorMsg && <Alert tone="error" className="mt-5">{errorMsg}</Alert>}

            {/* ── Controls ── */}
            <div className="mt-6 flex flex-col items-center gap-3">
                {enrollPhase === "face" && faceModelsLoading && (
                    <p className="flex items-center gap-2 text-sm text-ink-2" role="status">
                        <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />
                        {l("بنجهّز المسح…", "Getting ready…")}
                    </p>
                )}

                {enrollPhase === "face" && !faceScanning && !faceModelsLoading && faceModelsReady && step !== "error" && (
                    <label className="flex w-full cursor-pointer items-start gap-3 rounded-[var(--radius-control)] border border-rule bg-sheet-2 p-3.5 text-start text-sm text-ink-2">
                        <input
                            type="checkbox"
                            checked={consent}
                            onChange={(e) => setConsent(e.target.checked)}
                            className="mt-0.5 size-[18px] shrink-0 accent-[var(--pen)]"
                        />
                        <span>
                            {l("أوافق إن OralIQ يحفظ بصمة وشّي وصوتي ويستخدمها للتأكد من هويتي في الامتحانات بس. البصمة بتتحفظ كأرقام مش كصور أو تسجيلات، ومحدش يقدر يغيّرها غير بإذن المحاضر.",
                                "I agree that OralIQ stores my face and voice prints and uses them only to confirm my identity in exams. Prints are stored as numbers, not photos or recordings, and can only be changed with lecturer approval.")}
                        </span>
                    </label>
                )}

                {enrollPhase === "face" && !faceScanning && !faceModelsLoading && faceModelsReady && step !== "error" && (
                    <Button size="lg" className="w-full sm:w-auto" onClick={startFaceScan} disabled={!consent}>
                        <ScanFace className="size-5" aria-hidden />{l("امسح وشي", "Scan my face")}
                    </Button>
                )}

                {enrollPhase === "voice" && step === "idle" && (
                    <Button size="lg" className="w-full sm:w-auto" onClick={startRecording}>
                        <Mic className="size-5" aria-hidden />
                        {completedCount === 0
                            ? l(`ابدأ التسجيل (${RECORD_SECONDS} ثواني)`, `Start recording (${RECORD_SECONDS}s)`)
                            : l(`سجّل الجملة ${phraseIndex + 1}`, `Record sentence ${phraseIndex + 1}`)}
                    </Button>
                )}

                {step === "recording" && (
                    <div className="flex w-full max-w-xs flex-col items-center gap-3" role="status">
                        <span className="relative flex size-14 items-center justify-center">
                            <span className="absolute inset-0 rounded-full bg-mark/20 motion-safe:animate-[oiq-pulse-ring_1.4s_ease-out_infinite]" />
                            <span className="relative flex size-14 items-center justify-center rounded-full bg-mark text-white"><Mic className="size-6" aria-hidden /></span>
                        </span>
                        <p className="font-semibold text-mark tabular">{l(`بنسجّل… ${RECORD_SECONDS - recordingTime} ثانية`, `Recording… ${RECORD_SECONDS - recordingTime}s`)}</p>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-rule">
                            <div className="h-full rounded-full bg-mark transition-[width] duration-300" style={{ width: `${progress}%` }} />
                        </div>
                    </div>
                )}

                {step === "uploading" && (
                    <p className="flex items-center gap-2 text-ink-2" role="status">
                        <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />
                        {l("بنحفظ بصمة صوتك…", "Saving your voiceprint…")}
                    </p>
                )}

                {step === "success" && (
                    <div className="flex flex-col items-center gap-3 py-4 text-center" role="status">
                        <DrawnCheck className="size-16 text-pass" />
                        <p className="font-semibold">{l("تمام! تقدر تدخل امتحاناتك دلوقتي.", "All set — you can take your exams now.")}</p>
                    </div>
                )}

                {step === "error" && (
                    <Button variant="secondary" onClick={retry}>
                        <RefreshCw className="size-4" aria-hidden />
                        {enrollPhase === "face"
                            ? l("جرّب المسح تاني", "Try the scan again")
                            : recordedBlobs.length >= totalPhrases
                                ? l("جرّب الحفظ تاني", "Try saving again")
                                : l(`سجّل الجملة ${phraseIndex + 1} تاني`, `Record sentence ${phraseIndex + 1} again`)}
                    </Button>
                )}
            </div>
        </Modal>
    );
}
