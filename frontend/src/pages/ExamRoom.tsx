import { useState, useRef, useEffect, useCallback } from "react";

import { useNavigate } from "react-router-dom";

import { AlertCircle, Camera, Eye, Lightbulb, Mic, PhoneOff, ScanFace, Square, Volume2, Wifi } from "lucide-react";

import Logo, { LogoMark } from "../components/Logo";

import LanguageToggle, { ThemeToggle } from "../components/LanguageToggle";

import VoiceEnrollmentModal from "../components/VoiceEnrollmentModal";

import { PageLoader } from "../components/PageLoader";

import { LiveWaveform } from "../components/exam/LiveWaveform";

import { BreathingCoach } from "../components/exam/BreathingCoach";

import { Button } from "../components/ui/button";

import { Field, Input } from "../components/ui/input";

import { Panel } from "../components/ui/panel";

import { Alert } from "../components/ui/feedback";

import { Badge } from "../components/ui/badge";

import { ScoreMark } from "../components/ui/score-mark";

import { encouragementOf, studentGradeOf } from "../lib/grades";

import { countOf, NOUNS } from "../lib/format";

import { usePageTitle } from "../lib/usePageTitle";

import { useFieldErrors } from "../lib/useFieldErrors";

import { getApiErrorMessage } from "../lib/apiErrors";

import { DrawnCheck } from "../components/motion";

import { cn } from "../lib/utils";



import api from "../lib/api";

import { useI18n } from "../i18n";

import { buildFaceVerifyForm } from "../lib/faceBiometrics";



// ─── Types ────────────────────────────────────────────────────────────────────



type Phase = "loading" | "voice_required" | "info" | "preview" | "recording" | "processing" | "done" | "failed";



/** A fresh id for one recording. randomUUID is missing on older Safari and Chrome, hence the fallback. */

function newSubmissionKey(): string {

    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();

    const bytes = new Uint8Array(16);

    crypto.getRandomValues(bytes);

    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

}



interface ExamQuestion {

    id: number;

    text: string;

    exam_id: number | null;

    timeLimit: number;

    model_answer?: string;

}



interface ExamResult {

    transcript: string;

    nlp_score: number;

    speech_score: number;

    facial_score: number | null;

    overall_score: number;

}



type GradingStatus = "queued" | "processing" | "completed" | "failed";

/** Where the grading of the answer just sent stands (graded by a worker, not by the submit request). */
interface GradingInfo {
    submissionId: number;
    status: GradingStatus;
    queueAhead: number | null;
    attempts: number;
    unreachable: boolean;
}

/** The answer waiting for its grade, remembered so a reload or a dropped connection can pick it up again. */
const PENDING_GRADING_KEY = "oraliq.pendingGrading";

interface PendingGrading {
    examToken: string;
    questionId: number;
    submissionId: number;
    submissionKey: string;
}

const readPendingGrading = (): PendingGrading | null => {
    try { return JSON.parse(localStorage.getItem(PENDING_GRADING_KEY) || "null"); } catch { return null; }
};

const resultOf = (d: any): ExamResult => ({
    transcript: d.transcript || "",
    nlp_score: d.nlp_score ?? 0,
    speech_score: d.speech_score ?? 0,
    // null = integrity not measured by the server: shown as "—", never as 100.
    facial_score: d.facial_score ?? null,
    overall_score: d.overall_score ?? 0,
});



// ─── Component ────────────────────────────────────────────────────────────────



export default function ExamRoom() {

    const { t, l, lang } = useI18n();

    const navigate = useNavigate();

    // The invite token is cleared once the last answer is in; an answer still being graded keeps
    // its own copy so a reload can return to it.
    const examToken = localStorage.getItem("pendingExamToken") || readPendingGrading()?.examToken || "";



    // ── UI state ──────────────────────────────────────────────────────────────

    const [phase, setPhase] = useState<Phase>("loading");

    const [guideAccepted, setGuideAccepted] = useState(false);

    const [question, setQuestion] = useState<ExamQuestion | null>(null);

    const [allQuestions, setAllQuestions] = useState<ExamQuestion[]>([]);

    const [currentQIndex, setCurrentQIndex] = useState(0);

    const [studentName, setStudentName] = useState("");

    const [studentId, setStudentId] = useState("");

    const [errorMsg, setErrorMsg] = useState("");

    // Check-in step: name and student number, each with its own message

    const detailsRef = useRef<HTMLDivElement>(null);

    const { errors: detailErrors, validate: checkDetails, clear: clearDetail } = useFieldErrors();

    const [timeLeft, setTimeLeft] = useState(120);

    const [result, setResult] = useState<ExamResult | null>(null);

    const [grading, setGrading] = useState<GradingInfo | null>(null);

    // The last recording, kept so a failed upload can be sent again under the same submission key.
    const lastBlobRef = useRef<Blob | null>(null);

    const [canResend, setCanResend] = useState(false);



    const [stream, setStream] = useState<MediaStream | null>(null);



    // ── Stable refs ───────────────────────────────────────────────────────────

    const videoRef = useRef<HTMLVideoElement>(null);

    const canvasRef = useRef<HTMLCanvasElement>(null);

    const recorderRef = useRef<MediaRecorder | null>(null);

    const chunksRef = useRef<Blob[]>([]);

    const startedAtRef = useRef("");

    // The server-timed sitting (access-check): when it ends, in this device's clock. A reload gets
    // the same deadline back from the server, so the time left never resets.
    const sessionDeadlineRef = useRef<number | null>(null);
    const sessionSecondsLeft = () =>
        sessionDeadlineRef.current == null ? Infinity : Math.max(0, Math.floor((sessionDeadlineRef.current - Date.now()) / 1000));

    // One id per recording, sent with every attempt to submit it. Grading can outlast the request

    // timeout below, so without it a retry of a submission that actually succeeded would be graded

    // again and the lecturer would see the same answer twice.

    const submissionKeyRef = useRef("");

    const phaseRef = useRef<Phase>("loading");



    // anti-cheat (exact names from original OralIQ repo)

    const antiCheatAlertsRef = useRef<Record<string, number>>({});

    const lastFrameTimeRef = useRef<number>(performance.now());

    const lastAlertTimeRef = useRef<number>(0);

    const lastAlertTypeRef = useRef<string>("");

    const alertSequenceRef = useRef(0);

    const detectionGenRef = useRef(0);

    const faceMeshWarmRef = useRef<any>(null);

    const faceMeshWarmPromiseRef = useRef<Promise<void> | null>(null);

    const objectDetectorRef = useRef<any>(null);

    const faceScoresRef = useRef<number[]>([]);

    const hasServerFaceRef = useRef(false);



    // live alert popup (single string, 4s throttle — same as original)

    const [liveAlert, setLiveAlert] = useState<string | null>(null);

    /** A calm nudge, not an accusation: say what to do, not what went wrong. */

    const alertText = (type: string) => {

        switch (type) {

            case "no_face": return l("خلّي وشك ظاهر في الكاميرا", "Keep your face in the camera");

            case "multiple_people": return l("لازم تكون لوحدك في الكادر", "Only you should be in view");

            case "phone_detected": return l("بعّد الموبايل عن الكاميرا", "Put the phone out of view");

            case "book_detected": return l("بعّد الورق والكتب", "Put notes and books away");

            case "face_mismatch": return l("الوش مش مطابق للي متسجّل", "Face doesn't match your registration");

            default: return l("رجّع عينك للشاشة", "Eyes back on the screen");

        }

    };

    const [showEnroll, setShowEnroll] = useState(false);

    usePageTitle(l("الامتحان", "Exam"));



    // Remaining pending assignments

    const [remainingExams, setRemainingExams] = useState<{ exam_token: string; question_text: string }[]>([]);



    // keep phaseRef in sync

    useEffect(() => { phaseRef.current = phase; }, [phase]);



    // ── Move on to the next assigned exam (if any) ───────────────────────────

    const goToNextExam = useCallback(async () => {

        try {

            const { data } = await api.get("/exams/my-assignments");

            const remaining = (data || []).filter((a: any) => a.exam_token && a.exam_token !== examToken);

            if (remaining.length === 0) {

                navigate("/dashboard");

                return;

            }

            const next = remaining[0];

            localStorage.setItem("pendingExamToken", next.exam_token);

            // Hard reload so state resets cleanly

            window.location.assign("/exam/start");

        } catch {

            navigate("/dashboard");

        }

    }, [examToken, navigate]);



    // ── Grading status of the answer just sent ───────────────────────────────
    const applyGradingStatus = (d: any) => {
        const status = (d?.grading_status || "queued") as GradingStatus;
        setGrading({
            submissionId: d.id,
            status,
            queueAhead: d.queue_ahead ?? null,
            attempts: d.attempts ?? 0,
            unreachable: false,
        });
        // Shown only when the server released it (immediate exam, or results published). Otherwise
        // the server sends no grade at all, and the screen says it is waiting for the lecturer.
        setResult(status === "completed" && d?.result_visible === true ? resultOf(d) : null);
    };

    const forgetPendingGrading = () => localStorage.removeItem(PENDING_GRADING_KEY);

    // Poll until the worker has finished (or given up on) this answer. A failed poll is not an
    // error for the student: the answer is already stored, so keep asking, a little slower.
    const gradingSubmissionId = grading?.submissionId;
    const gradingStatus = grading?.status;
    const gradingUnreachable = grading?.unreachable;
    const [pollTick, setPollTick] = useState(0);
    const [sessionLost, setSessionLost] = useState(false);
    useEffect(() => {
        if (phase !== "done" || !gradingSubmissionId || sessionLost) return;
        if (gradingStatus === "completed" || gradingStatus === "failed") return;
        let cancelled = false;
        const id = setTimeout(async () => {
            try {
                const { data } = await api.get(`/exams/submissions/${gradingSubmissionId}/grading`);
                if (!cancelled) applyGradingStatus(data);
            } catch (e: any) {
                if (cancelled) return;
                const st = e?.response?.status;
                if (st === 401 || st === 403) {
                    // The answer is stored; only following its grade here needs a new sign-in.
                    setSessionLost(true);
                    return;
                }
                setGrading((g) => g && { ...g, unreachable: true });
            }
            if (!cancelled) setPollTick((n) => n + 1);
        }, gradingUnreachable ? 6000 : 3000);
        return () => { cancelled = true; clearTimeout(id); };
    }, [phase, gradingSubmissionId, gradingStatus, gradingUnreachable, pollTick, sessionLost]);



    // ── Connect stream to video element whenever stream changes ───────────────

    useEffect(() => {

        if (stream && videoRef.current) {

            videoRef.current.srcObject = stream;

            videoRef.current.play().catch(() => {});

        }

    }, [stream]);



    // ── Auth + question load ──────────────────────────────────────────────────

    useEffect(() => {

        const token = localStorage.getItem("token");

        if (!token) { navigate("/login"); return; }



        const buildQ = (q: any): ExamQuestion => ({

            id: q.id,

            text: q.text,

            exam_id: q.exam_id ?? null,

            timeLimit: (q.duration_minutes || 2) * 60,

            model_answer: q.model_answer || "",

        });



        const loadExam = async () => {

            try {

                const res = await api.get("/users/me");

                setStudentName(res.data.full_name || "");



                api.get("/exams/my-assignments")

                    .then(r => setRemainingExams(

                        (r.data || []).map((a: any) => ({

                            exam_token: a.exam_token,

                            question_text: a.question_text || "",

                        })).filter((a: any) => a.exam_token)

                    ))

                    .catch(() => {});



                // Only students taking exams require voice and face biometric enrollment.
                // Doctors/lecturers previewing or testing their questions bypass biometric gating.
                const isStudent = res.data?.role === "student";

                if (isStudent) {
                    try {
                        const vr = await api.get("/voice/status");
                        if (!vr.data.biometrics_complete) {
                            setPhase("voice_required");
                            return;
                        }
                        hasServerFaceRef.current = !!vr.data.has_faceprint;
                    } catch {
                        setPhase("voice_required");
                        return;
                    }
                }



                if (!examToken) {

                    setErrorMsg(t("exam.noQuestion"));

                    setPhase("info");

                    return;

                }



                let loaded: ExamQuestion[] = [];

                try {

                    const { data: groupData } = await api.get(`/questions/by-group/${examToken}`).catch(() => ({ data: null }));

                    if (groupData && Array.isArray(groupData) && groupData.length > 0) {

                        const built = groupData.map(buildQ);

                        loaded = built;

                        setAllQuestions(built);

                        setQuestion(built[0]);

                        setCurrentQIndex(0);

                    } else {

                        const { data } = await api.get(`/questions/by-token/${examToken}`);

                        const built = buildQ(data);

                        loaded = [built];

                        setAllQuestions([built]);

                        setQuestion(built);

                        setCurrentQIndex(0);

                    }

                } catch {

                    setErrorMsg(t("exam.noQuestion"));

                }

                // Back after a reload or a dropped connection while an answer was being graded:
                // show that answer's grading again instead of starting the exam over.
                const pending = readPendingGrading();
                if (pending && pending.examToken === examToken) {
                    const idx = loaded.findIndex((q) => q.id === pending.questionId);
                    try {
                        const { data } = await api.get(`/exams/submissions/${pending.submissionId}/grading`);
                        if (idx >= 0) {
                            submissionKeyRef.current = pending.submissionKey;
                            setCurrentQIndex(idx);
                            setQuestion(loaded[idx]);
                            applyGradingStatus(data);
                            setPhase("done");
                            return;
                        }
                    } catch (e: any) {
                        if (e?.response?.status === 404) localStorage.removeItem(PENDING_GRADING_KEY);
                    }
                }



                // Starts — or after a reload resumes — the server-timed sitting, and reports up front
                // anything that stops the student: plan seats full (402), face/voice not enrolled
                // (403), attempts used up (409).
                try {
                    const { data: access } = await api.get(`/exams/access-check/${examToken}`);
                    const session = access?.session;
                    if (session) {
                        sessionDeadlineRef.current = Date.now() + Math.max(0, session.remaining_seconds) * 1000;
                        const answered: number[] = session.answered_question_ids || [];
                        const next = loaded.findIndex((q) => !answered.includes(q.id));
                        if (session.remaining_seconds <= 0) {
                            setErrorMsg(l("وقت الامتحان خلص.", "The exam time is over."));
                            setAllQuestions([]);
                            setQuestion(null);
                        } else if (answered.length && next > 0) {
                            // Already answered in this sitting: continue from the first open question.
                            setCurrentQIndex(next);
                            setQuestion(loaded[next]);
                        }
                    }
                } catch (accessErr: any) {
                    const st = accessErr?.response?.status;
                    if (st === 402 || st === 403 || st === 409) {
                        setErrorMsg(getApiErrorMessage(accessErr));
                        setAllQuestions([]);
                        setQuestion(null);
                    }
                }



                setPhase("info");

            } catch (err: any) {

                const status = err?.response?.status;

                if (status === 401 || status === 403) {

                    localStorage.removeItem("token");

                    navigate("/login", { replace: true });

                    return;

                }

                setErrorMsg(t("exam.noQuestion"));

                setPhase("info");

            }

        };



        loadExam();

    }, []);



    // Preload FaceMesh WASM while student is on the info screen — landmarks ready instantly

    const warmFaceMesh = useCallback(async () => {

        if (faceMeshWarmRef.current) return;

        const { FaceMesh } = await import("@mediapipe/face_mesh");

        const fm = new FaceMesh({

            locateFile: (file: string) =>

                `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`,

        });

        fm.setOptions({

            maxNumFaces: 1,

            refineLandmarks: true,

            minDetectionConfidence: 0.5,

            minTrackingConfidence: 0.5,

        });

        const warm = document.createElement("canvas");

        warm.width = 64;

        warm.height = 64;

        warm.getContext("2d")?.fillRect(0, 0, 64, 64);

        await fm.send({ image: warm });

        faceMeshWarmRef.current = fm;

    }, []);



    useEffect(() => {

        if (!faceMeshWarmPromiseRef.current) {

            faceMeshWarmPromiseRef.current = warmFaceMesh().catch(() => {

                faceMeshWarmPromiseRef.current = null;

            });

        }

    }, [warmFaceMesh]);



    // ── Timer (recording only) ────────────────────────────────────────────────

    useEffect(() => {

        if (phase !== "recording" || timeLeft <= 0) return;

        const id = setInterval(() => {

            setTimeLeft(p => {

                if (p <= 1) { forceStop(); return 0; }

                return p - 1;

            });

        }, 1000);

        return () => clearInterval(id);

    }, [phase, timeLeft]);



    // A question's own time, but never past the end of the server-timed sitting.
    useEffect(() => { if (question) setTimeLeft(Math.min(question.timeLimit, sessionSecondsLeft())); }, [question]);



    // ── accumulateDistraction: exact copy from original OralIQ repo ─────────

    const accumulateDistraction = (type: string, dt: number) => {

        antiCheatAlertsRef.current[type] = (antiCheatAlertsRef.current[type] || 0) + dt;

        const now = Date.now();

        // Show a new direction immediately; throttle only repeats of the same alert.

        if (type !== lastAlertTypeRef.current || now - lastAlertTimeRef.current > 1500) {

            // Store the kind of alert; the wording is chosen at render time (see alertText).

            setLiveAlert(type);

            lastAlertTimeRef.current = now;

            lastAlertTypeRef.current = type;

            const sequence = ++alertSequenceRef.current;

            setTimeout(() => {

                if (alertSequenceRef.current === sequence) setLiveAlert(null);

            }, 1000);

        }

    };



    const initFaceMesh = async () => {

        const gen = ++detectionGenRef.current;



        // Use pre-warmed instance if available (WASM already loaded)

        try {

            if (faceMeshWarmPromiseRef.current) await faceMeshWarmPromiseRef.current;

        } catch { /* fall through to fresh create */ }



        const procCanvas = document.createElement("canvas");

        procCanvas.width  = 640;

        procCanvas.height = 480;

        const procCtx = procCanvas.getContext("2d")!;



        // Real-time local gaze. MediaPipe runs every frame; server polling is too

        // delayed for pupil movement and can report a stale direction.

        const SMOOTH_N = 3;

        const bufHH: number[] = [], bufHV: number[] = [];

        const bufPH: number[] = [], bufPV: number[] = [], bufEyeV: number[] = [];

        const gazeCenter = { samples: 0, h: 0.5, v: 0.5, eyeV: 0 };

        let downHold = 0;

        let noFaceHold = 0;

        const smooth = (buf: number[], val: number) => {

            buf.push(val);

            if (buf.length > SMOOTH_N) buf.shift();

            return buf.reduce((a, b) => a + b, 0) / buf.length;

        };

        const normalizeBetween = (value: number, a: number, b: number) => {

            const min = Math.min(a, b);

            const max = Math.max(a, b);

            return (value - min) / Math.max(max - min, 1e-6);

        };



        let faceMesh = faceMeshWarmRef.current;

        if (!faceMesh) {

            const { FaceMesh } = await import("@mediapipe/face_mesh");

            faceMesh = new FaceMesh({

                locateFile: (file: string) =>

                    `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`,

            });

            faceMesh.setOptions({

                maxNumFaces: 1,

                refineLandmarks: true,

                minDetectionConfidence: 0.5,

                minTrackingConfidence: 0.5,

            });

            faceMeshWarmRef.current = faceMesh;

        }



        if (!objectDetectorRef.current) {

            (async () => {

                try {

                    const { ObjectDetector, FilesetResolver } = await import("@mediapipe/tasks-vision");

                    const vision = await FilesetResolver.forVisionTasks(

                        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm"

                    );

                    objectDetectorRef.current = await ObjectDetector.createFromOptions(vision, {

                        baseOptions: {

                            modelAssetPath:

                                "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite",

                            delegate: "CPU",

                        },

                        scoreThreshold: 0.5,

                        runningMode: "VIDEO",

                    });

                } catch (e) {

                    console.warn("[ObjectDetector] load failed:", e);

                }

            })();

        }



        faceMesh.onResults((results: any) => {

            const currentPhase = phaseRef.current;

            if (currentPhase !== "preview" && currentPhase !== "recording") return;

            const isRecording = currentPhase === "recording";



            const now = performance.now();

            const dt = Math.min(Math.max((now - lastFrameTimeRef.current) / 1000, 0), 0.12);



            if (!results.multiFaceLandmarks || results.multiFaceLandmarks.length === 0) {

                noFaceHold += dt;

                if (isRecording && noFaceHold >= 0.8) accumulateDistraction("no_face", dt);

                const canvas = canvasRef.current;

                if (canvas) canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);

                return;

            }

            noFaceHold = 0;

            if (isRecording && results.multiFaceLandmarks.length > 1) {

                accumulateDistraction("multiple_people", dt);

            }



            const lm = results.multiFaceLandmarks[0];

            const nose = lm[1], mouth = lm[14];

            const leftEye = lm[33], rightEye = lm[263];

            const rawHH = (nose.x - leftEye.x) / Math.max(rightEye.x - leftEye.x, 1e-6);

            const rawHV = (nose.y - leftEye.y) / Math.max(mouth.y - nose.y, 1e-6);

            const lOuter = lm[33],  lInner = lm[133], lTop = lm[159], lBot = lm[145];

            const rOuter = lm[263], rInner = lm[362], rTop = lm[386], rBot = lm[374];

            const liris = lm[468], riris = lm[473];

            if (!liris || !riris) return;



            const rawPH = (

                normalizeBetween(liris.x, lOuter.x, lInner.x) +

                normalizeBetween(riris.x, rOuter.x, rInner.x)

            ) / 2;

            const rawPV = (

                normalizeBetween(liris.y, lTop.y, lBot.y) +

                normalizeBetween(riris.y, rTop.y, rBot.y)

            ) / 2;

            // Vertical pupil offset relative to eye corners. Corners stay much

            // more stable than eyelids, which move with the pupil up/down.

            const eyeVerticalOffset = (

                iris: { x: number; y: number },

                outer: { x: number; y: number },

                inner: { x: number; y: number },

            ) => {

                const centerY = (outer.y + inner.y) / 2;

                const eyeWidth = Math.max(

                    Math.hypot(inner.x - outer.x, inner.y - outer.y),

                    1e-6,

                );

                return (iris.y - centerY) / eyeWidth;

            };

            const rawEyeV = (

                eyeVerticalOffset(liris, lOuter, lInner) +

                eyeVerticalOffset(riris, rOuter, rInner)

            ) / 2;

            const eyeOpenness = (

                top: { x: number; y: number },

                bot: { x: number; y: number },

                outer: { x: number; y: number },

                inner: { x: number; y: number },

            ) => {

                const lidGap = Math.hypot(bot.x - top.x, bot.y - top.y);

                const eyeWidth = Math.max(

                    Math.hypot(inner.x - outer.x, inner.y - outer.y),

                    1e-6,

                );

                return lidGap / eyeWidth;

            };

            // A blink collapses the lid gap and makes the iris landmark jump upward.

            const eyesClosed = (

                eyeOpenness(lTop, lBot, lOuter, lInner) +

                eyeOpenness(rTop, rBot, rOuter, rInner)

            ) / 2 < 0.12;

            const hH = smooth(bufHH, rawHH);

            const hV = smooth(bufHV, rawHV);

            const pH = smooth(bufPH, rawPH);

            const pV = smooth(bufPV, rawPV);

            const eyeV = smooth(bufEyeV, rawEyeV);

            // Very short neutral calibration (~8 processed frames, typically <0.5s).

            if (gazeCenter.samples < 8) {

                gazeCenter.h = ((gazeCenter.h * gazeCenter.samples) + pH) / (gazeCenter.samples + 1);

                gazeCenter.v = ((gazeCenter.v * gazeCenter.samples) + pV) / (gazeCenter.samples + 1);

                gazeCenter.eyeV = ((gazeCenter.eyeV * gazeCenter.samples) + eyeV) / (gazeCenter.samples + 1);

                gazeCenter.samples += 1;

            } else if (isRecording) {

                const relH = pH - gazeCenter.h;

                const relV = pV - gazeCenter.v;

                const relEyeV = eyeV - gazeCenter.eyeV;



                // Right/left/up are immediate. Full head turns are also detected.

                const lookLeft = (!eyesClosed && relH > 0.11) || hH < 0.30;

                const lookRight = (!eyesClosed && relH < -0.11) || hH > 0.70;

                const lookUp = !eyesClosed && (relEyeV < -0.025 || relV < -0.07 || hV < 0.38);

                const lookDown = !eyesClosed && (relEyeV > 0.035 || relV > 0.09 || hV > 2.35);



                if (lookLeft) accumulateDistraction("gaze_left", dt);

                else if (lookRight) accumulateDistraction("gaze_right", dt);



                if (eyesClosed) {

                    // Natural blink: ignore this frame completely.

                    downHold = 0;

                } else if (lookUp) {

                    downHold = 0;

                    accumulateDistraction("gaze_up", dt);

                } else if (lookDown) {

                    // Down is delayed because the question/submit button are below

                    // the camera on phones. A quick read/tap is not suspicious.

                    downHold += dt;

                    if (downHold >= 1.2) accumulateDistraction("gaze_down", dt);

                } else {

                    downHold = 0;

                }



                // Slowly absorb tiny phone-angle drift only while clearly centered.

                if (!lookLeft && !lookRight && !lookUp && !lookDown) {

                    gazeCenter.h = gazeCenter.h * 0.995 + pH * 0.005;

                    gazeCenter.v = gazeCenter.v * 0.995 + pV * 0.005;

                    gazeCenter.eyeV = gazeCenter.eyeV * 0.995 + eyeV * 0.005;

                }

            }



            const canvas = canvasRef.current;

            if (canvas && isRecording) {

                const ctx = canvas.getContext("2d");

                if (ctx) {

                    const W = canvas.width, H = canvas.height;

                    ctx.clearRect(0, 0, W, H);

                    const totalAcc = Object.values(antiCheatAlertsRef.current).reduce((a, b) => a + b, 0);

                    const color = totalAcc > 3 ? "#ff4d4d" : totalAcc > 0.5 ? "#e0e0e0" : "#4ade80";

                    ctx.fillStyle = color;

                    ctx.globalAlpha = 0.55;

                    for (const p of lm) {

                        ctx.beginPath();

                        ctx.arc(p.x * W, p.y * H, 1.1, 0, Math.PI * 2);

                        ctx.fill();

                    }

                    ctx.globalAlpha = 1;



                    [

                        { iris: liris, outer: lOuter, inner: lInner, top: lTop, bot: lBot },

                        { iris: riris, outer: rOuter, inner: rInner, top: rTop, bot: rBot },

                    ].forEach(({ iris, outer, inner, top, bot }) => {

                        const minX = Math.min(outer.x, inner.x) * W;

                        const maxX = Math.max(outer.x, inner.x) * W;

                        const minY = Math.min(top.y, bot.y) * H;

                        const maxY = Math.max(top.y, bot.y) * H;

                        const neutralX = minX + gazeCenter.h * (maxX - minX);

                        const neutralY = minY + gazeCenter.v * (maxY - minY);

                        const irisX = iris.x * W;

                        const irisY = iris.y * H;

                        const active =

                            Math.abs(irisX - neutralX) > (maxX - minX) * 0.14 ||

                            Math.abs(irisY - neutralY) > (maxY - minY) * 0.16;



                        ctx.strokeStyle = active ? "#ff4d5d" : "#4ade80";

                        ctx.lineWidth = 2.5;

                        ctx.beginPath();

                        ctx.moveTo(neutralX, neutralY);

                        ctx.lineTo(irisX, irisY);

                        ctx.stroke();

                        ctx.beginPath();

                        ctx.arc(irisX, irisY, 6.5, 0, Math.PI * 2);

                        ctx.fillStyle = active ? "#ff4d5d" : "#ffffff";

                        ctx.fill();

                        ctx.strokeStyle = "#0a0a0a";

                        ctx.lineWidth = 1.5;

                        ctx.stroke();

                    });

                }

            }

        });



        const runDetection = async () => {

            if (detectionGenRef.current !== gen) return;

            try {

                const video = videoRef.current;

                if (video && video.readyState >= 2) {

                    const now = performance.now();

                    procCanvas.width  = video.videoWidth  || 640;

                    procCanvas.height = video.videoHeight || 480;

                    procCtx.drawImage(video, 0, 0);

                    await faceMesh.send({ image: procCanvas });



                    if (phaseRef.current === "recording" && objectDetectorRef.current) {

                        const detections = objectDetectorRef.current.detectForVideo(video, now);

                        for (const detection of detections.detections) {

                            const label = (detection.categories[0]?.categoryName || "").toLowerCase();

                            const dt2 = Math.min((now - lastFrameTimeRef.current) / 1000, 0.12);

                            if (["cell phone", "mobile phone", "phone"].includes(label)) {

                                accumulateDistraction("phone_detected", dt2);

                            } else if (["book", "notebook"].includes(label)) {

                                accumulateDistraction("book_detected", dt2);

                            }

                        }

                    }

                    lastFrameTimeRef.current = now;

                }

            } catch (e) {

                console.warn("[runDetection] frame error:", e);

            }

            if (detectionGenRef.current === gen) {

                requestAnimationFrame(runDetection);

            }

        };

        requestAnimationFrame(runDetection);

    };



    // Calibrate silently during preview; draw/monitor only while recording.

    useEffect(() => {

        if (stream) {

            initFaceMesh();

            return;

        }

        detectionGenRef.current++;

        const canvas = canvasRef.current;

        canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);

    }, [stream]);



    // InsightFace verification during recording. Gaze stays local for real-time response.

    useEffect(() => {

        if (phase !== "recording" || !stream) return;



        faceScoresRef.current = [];

        let cancelled = false;

        let faceBusy = false;



        const checkFace = async () => {

            if (cancelled || faceBusy || !hasServerFaceRef.current) return;

            const video = videoRef.current;

            if (!video || video.readyState < 2) return;

            faceBusy = true;

            try {

                const fd = await buildFaceVerifyForm(video, examToken);

                const { data } = await api.post("/face/verify", fd, {

                    headers: { "Content-Type": "multipart/form-data" },

                    timeout: 45_000,

                });

                if (typeof data?.similarity_score === "number") {

                    faceScoresRef.current.push(data.similarity_score);

                }

                if (data?.no_face) {

                    accumulateDistraction("no_face", 1.2);

                } else if (data?.status === "mismatch" || (

                    data?.similarity_score != null && data.similarity_score < 45

                )) {

                    accumulateDistraction("face_mismatch", 1.2);

                }

            } catch { /* transient */ }

            finally { faceBusy = false; }

        };



        checkFace();

        const faceIv = setInterval(checkFace, 4000);

        return () => {

            cancelled = true;

            clearInterval(faceIv);

        };

    }, [phase, stream]);



    // ── START EXAM: info → preview ────────────────────────────────────────────

    const startExam = useCallback(async () => {

        if (!checkDetails(detailsRef.current)) return;

        if (!question) { setErrorMsg(t("exam.noQuestion")); return; }

        setErrorMsg("");



        try {

            await api.get("/users/me");

        } catch (e: any) {

            const status = e?.response?.status;

            if (status === 401 || status === 403) {

                localStorage.removeItem("token");

                setErrorMsg(t("exam.sessionExpired"));

                return;

            }

        }



        let s: MediaStream;

        try {

            try {

                s = await navigator.mediaDevices.getUserMedia({

                    video: {

                        facingMode: "user",

                        width: { ideal: 960 },

                        height: { ideal: 960 },

                    },

                    audio: {

                        echoCancellation: true,

                        noiseSuppression: true,

                        autoGainControl: true,

                    },

                });

            } catch {

                s = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });

            }

        } catch {

            setErrorMsg(t("exam.permission"));

            return;

        }



        setStream(s);

        if (videoRef.current) {

            videoRef.current.srcObject = s;

            videoRef.current.play().catch(() => {});

        }

        setPhase("preview");

        phaseRef.current = "preview";



        // Reset anti-cheat counters

        antiCheatAlertsRef.current = {};

        lastFrameTimeRef.current = performance.now();

        lastAlertTimeRef.current = 0;

    }, [studentName, studentId, question, checkDetails]);



    // ── START RECORDING: preview → recording ─────────────────────────────────

    const startRecording = useCallback(() => {

        if (!stream) return;

        if (sessionSecondsLeft() <= 0) {
            // The server would refuse the answer: say so now instead of after a recording.
            setErrorMsg(l("وقت الامتحان خلص.", "The exam time is over."));
            return;
        }

        setErrorMsg("");

        startedAtRef.current = new Date().toISOString();

        chunksRef.current = [];



        const audioOnly = new MediaStream(stream.getAudioTracks());

        const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")

            ? "audio/webm;codecs=opus" : "audio/webm";

        const rec = new MediaRecorder(audioOnly, { mimeType: mime });

        rec.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };

        rec.start(100);

        recorderRef.current = rec;

        // Fresh timers — preview wait must not count as gaze/violation time

        antiCheatAlertsRef.current = {};

        faceScoresRef.current = [];

        lastFrameTimeRef.current = performance.now();

        lastAlertTimeRef.current = 0;

        lastAlertTypeRef.current = "";

        // Time spent reading counts on the server clock: the recording gets what is left of both.
        setTimeLeft((p) => Math.min(p, sessionSecondsLeft()));

        setPhase("recording");

        phaseRef.current = "recording";

    }, [stream]);



    // ── STOP + SUBMIT ─────────────────────────────────────────────────────────

    const stopAndSubmit = useCallback(() => {

        const rec = recorderRef.current;

        if (!rec || rec.state !== "recording") return;



        rec.onstop = async () => {

            // Guarantee at least one Face ID reading before releasing the camera.

            const video = videoRef.current;

            if (hasServerFaceRef.current && video && video.readyState >= 2) {

                try {

                    const fd = await buildFaceVerifyForm(video, examToken);

                    const { data } = await api.post("/face/verify", fd, {

                        headers: { "Content-Type": "multipart/form-data" },

                        timeout: 45_000,

                    });

                    if (typeof data?.similarity_score === "number") {

                        faceScoresRef.current.push(data.similarity_score);

                    }

                } catch {

                    // Submission still succeeds; report will show no valid Face ID reading.

                }

            }



            // Stop camera (RAF loop stops itself when video disappears)

            stream?.getTracks().forEach(t => t.stop());

            setStream(null);



            const blob = new Blob(chunksRef.current, { type: "audio/webm" });

            if (blob.size < 500) {

                setErrorMsg(l("التسجيل قصير شوية. اضغط «ابدأ الإجابة» واتكلم براحتك.", "That recording was a little short. Press Start answering and take your time."));

                setPhase("preview");

                return;

            }

            setPhase("processing");

            submissionKeyRef.current = newSubmissionKey();

            lastBlobRef.current = blob;

            await submitToBackend(blob);

        };

        rec.stop();

    }, [stream]);



    const forceStop = useCallback(() => {

        if (recorderRef.current?.state === "recording") stopAndSubmit();

    }, [stopAndSubmit]);



    // ── Submit to backend ─────────────────────────────────────────────────────

    // Submits the answer; only marks the exam as "done" on a real success

    // (response carries an id). Anything else -> "failed" with the actual error.

    const submitToBackend = async (blob: Blob) => {

        if (!question?.id) {

            setErrorMsg(l("السؤال ماتحمّلش. افتح رابط الامتحان تاني.", "The question didn't load. Open the exam link again."));

            setPhase("failed");

            return;

        }

        const finishedAt = new Date().toISOString();

        const recSec = Math.max(

            1,

            (new Date(finishedAt).getTime() - new Date(startedAtRef.current).getTime()) / 1000

        );

        const clampedAlerts: Record<string, number> = {};

        for (const [k, v] of Object.entries(antiCheatAlertsRef.current)) {

            clampedAlerts[k] = Math.min(v, recSec);

        }



        const fd = new FormData();

        fd.append("question_id", String(question.id));

        fd.append("student_name", studentName);

        fd.append("student_number", studentId);

        fd.append("audio", blob, "answer.webm");

        fd.append("anti_cheat_alerts", JSON.stringify(clampedAlerts));

        // No face_score: the server computes it from the face checks it recorded for this exam.

        fd.append("started_at", startedAtRef.current);

        fd.append("finished_at", finishedAt);

        if (submissionKeyRef.current) fd.append("submission_key", submissionKeyRef.current);



        setCanResend(false);

        try {

            // The server only stores the answer and queues it for grading, so this is an upload,
            // not a wait for the grade; the long timeout is for slow connections.
            const res = await api.post("/exams/submit", fd, {

                headers: { "Content-Type": "multipart/form-data" },

                timeout: 300_000,

            });

            if (res.data?.id) {

                lastBlobRef.current = null;

                localStorage.setItem(PENDING_GRADING_KEY, JSON.stringify({
                    examToken,
                    questionId: question.id,
                    submissionId: res.data.id,
                    submissionKey: submissionKeyRef.current,
                } satisfies PendingGrading));

                applyGradingStatus(res.data);

                // Check if there are more questions in the group

                const nextIdx = currentQIndex + 1;

                if (nextIdx < allQuestions.length) {

                    setPhase("done");

                } else {

                    localStorage.removeItem("pendingExamToken");

                    setPhase("done");

                }

            } else {

                setErrorMsg(l("إجابتك ماتسجلتش لأن السيرفر رد بشكل مش متوقع. جرّب تاني.", "Your answer wasn't saved because the server replied unexpectedly. Try again."));

                setPhase("failed");

            }

        } catch (e: any) {

            const status = e?.response?.status;

            if (status === 401 || status === 403) {

                localStorage.removeItem("token");

                setErrorMsg(t("exam.sessionExpired"));

                setPhase("failed");

                return;

            }

            // A calm, specific sentence for the student (never "error 500"); details stay in the console

            const msg = getApiErrorMessage(e, l("إجابتك ماتسجلتش. جرّب تاني.", "Your answer wasn't saved. Try again."));

            console.error("[ExamRoom] submit error:", status, e?.response?.data, e);

            setErrorMsg(msg);

            // No answer, a timeout or a server-side error: the recording is still here, and resending
            // it under the same key can never create a second answer (the server returns the first).
            setCanResend(!!lastBlobRef.current && (!status || status >= 500 || status === 429));

            setPhase("failed");

        }

    };



    // ── Cleanup on unmount ────────────────────────────────────────────────────

    useEffect(() => {

        return () => {

            stream?.getTracks().forEach(t => t.stop());

        };

    }, [stream]);



    // ─── Helpers ──────────────────────────────────────────────────────────────

    const mmss = (s: number) => `${Math.floor(Math.max(0, s) / 60)}:${String(Math.max(0, s) % 60).padStart(2, "0")}`;

    const totalMinutes = allQuestions.reduce((sum, q) => sum + Math.round(q.timeLimit / 60), 0);

    const multi = allQuestions.length > 1;

    const lowTime = phase === "recording" && timeLeft <= 30;

    const progress = question ? 1 - timeLeft / Math.max(question.timeLimit, 1) : 0;



    const goToNextQuestion = async () => {

        const nextIdx = currentQIndex + 1;

        setCurrentQIndex(nextIdx);

        setQuestion(allQuestions[nextIdx]);

        setTimeLeft(Math.min(allQuestions[nextIdx].timeLimit, sessionSecondsLeft()));

        setResult(null);

        setGrading(null);

        forgetPendingGrading();

        setErrorMsg("");

        antiCheatAlertsRef.current = {};

        lastFrameTimeRef.current = performance.now();

        lastAlertTimeRef.current = 0;

        // Re-request camera if stream died

        try {

            let s = stream;

            if (!s || !s.active) {

                s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 960 }, height: { ideal: 960 } }, audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });

                setStream(s);

            }

            if (videoRef.current) {

                videoRef.current.srcObject = s;

                videoRef.current.play().catch(() => {});

            }

        } catch { /* camera may still be available from before */ }

        setPhase("preview");

        phaseRef.current = "preview";

    };



    // ═════════════════════════════════════════════════════════════════════════

    //  UI

    // ═════════════════════════════════════════════════════════════════════════



    if (phase === "loading") return <PageLoader fullscreen />;



    if (phase === "voice_required") return (

        <Sheet>

            <Panel className="p-6 sm:p-8">

                <div className="mb-5 flex size-12 items-center justify-center rounded-full bg-warn-wash text-warn"><ScanFace className="size-6" aria-hidden /></div>

                <h1 className="text-2xl font-bold">{l("سجّل وجهك وصوتك الأول", "Register your face and voice first")}</h1>

                <p className="mt-2 text-ink-2">

                    {l("قبل أول امتحان لازم نسجّل شكل وشك ونبرة صوتك، عشان نتأكد إن انت اللي بتجاوب. بياخد حوالي دقيقتين ومرة واحدة بس.",

                        "Before your first exam we record your face and voice so we can confirm it's you answering. It takes about two minutes, once.")}

                </p>

                <Button size="lg" className="mt-6 w-full" onClick={() => setShowEnroll(true)}>{l("ابدأ التسجيل", "Start registration")}</Button>

                <Button variant="ghost" className="mt-2 w-full" onClick={() => navigate("/dashboard")}>{l("مش دلوقتي", "Not now")}</Button>

            </Panel>

            <VoiceEnrollmentModal isOpen={showEnroll} onClose={() => setShowEnroll(false)} onSuccess={() => window.location.reload()} />

        </Sheet>

    );



    if (phase === "info") return (

        <Sheet wide><div className="overflow-hidden rounded-[24px] border border-rule bg-sheet shadow-float"><div className="p-6 sm:p-8">

                <ol className="mb-6 flex items-center gap-2 text-xs font-medium text-ink-3" aria-label={l("خطوات الامتحان", "Exam steps")}>

                    {[l("بياناتك", "Your details"), l("الكاميرا", "Camera"), l("الإجابة", "Answer")].map((label, i) => (

                        <li key={label} aria-current={i === 0 ? "step" : undefined} className="flex items-center gap-2">

                            {i > 0 && <span className="h-px w-5 bg-rule-strong" aria-hidden />}

                            <span className={cn("flex size-5 items-center justify-center rounded-full font-display text-[0.6875rem]", i === 0 ? "bg-pen text-pen-ink" : "bg-sheet-2 text-ink-3 ring-1 ring-rule")}>{i + 1}</span>

                            <span className={i === 0 ? "text-ink" : undefined}>{label}</span>

                        </li>

                    ))}

                </ol>

                <h1 className="text-2xl font-bold">{l("قبل ما تبدأ", "Before you start")}</h1>

                {question ? (

                    <p className="mt-2 text-ink-2">

                        {multi

                            ? l(`الامتحان فيه ${countOf("ar", allQuestions.length, NOUNS.question)}، ومعاك حوالي ${countOf("ar", totalMinutes, NOUNS.minute)} للإجابة عليهم بصوتك.`, `This exam has ${allQuestions.length} questions — about ${totalMinutes} minutes of speaking.`)

                            : l(`سؤال واحد، ومعاك ${countOf("ar", totalMinutes, NOUNS.minute)} للإجابة بصوتك.`, `One question, with ${totalMinutes} minute${totalMinutes === 1 ? "" : "s"} to answer out loud.`)}

                    </p>

                ) : (

                    <p className="mt-2 text-ink-2">{l("أكّد بياناتك.", "Confirm your details.")}</p>

                )}



                {errorMsg && <Alert tone="error" className="mt-5">{errorMsg}</Alert>}



                <div ref={detailsRef} className="mt-6 grid gap-4">

                    <Field label={l("الاسم بالكامل", "Full name")} htmlFor="ex-name" error={detailErrors["ex-name"] && l("اكتب اسمك زي ما هو في الكشف.", "Write your name as it appears on the class list.")}>

                        <Input id="ex-name" required value={studentName} onChange={(e) => { setStudentName(e.target.value); clearDetail("ex-name"); }} autoComplete="name" />

                    </Field>

                    <Field label={l("الرقم الجامعي", "Student number")} htmlFor="ex-id" error={detailErrors["ex-id"] && l("اكتب رقمك الجامعي.", "Write your student number.")}>

                        <Input id="ex-id" required value={studentId} onChange={(e) => { setStudentId(e.target.value); clearDetail("ex-id"); }} inputMode="numeric" className="tabular" data-autofocus autoFocus />

                    </Field>

                </div>



                <section className="mt-6 rounded-2xl border border-sky-500/30 bg-sky-500/[0.07] p-4 sm:p-5" aria-labelledby="exam-guide-title">

                    <h2 id="exam-guide-title" className="mb-3 flex items-center gap-2 text-base font-bold text-ink">

                        <Lightbulb className="size-5 text-sky-600 dark:text-sky-400" aria-hidden />

                        {l("إرشادات مهمة قبل الامتحان", "Important tips before you start")}

                    </h2>

                    <ul className="grid gap-2.5 text-sm text-ink-2 sm:grid-cols-2">

                        {[

                            { icon: Volume2, text: l("اقعد في مكان هادي بعيد عن الدوشة والأصوات العالية.", "Sit somewhere quiet, away from noise.") },

                            { icon: Mic, text: l("اتكلم بصوت واضح ومسموع وبسرعة طبيعية، وقرّب من الميكروفون.", "Speak clearly at a normal pace, close to the microphone.") },

                            { icon: Lightbulb, text: l("خلي الإضاءة كويسة وقدّامك، مش وراك، عشان وشك يبان واضح.", "Use good light in front of you (not behind) so your face is clear.") },

                            { icon: Eye, text: l("بص على الشاشة طول الإجابة. النظر يمين وشمال كتير بيتسجل للدكتور.", "Keep looking at the screen — frequent looking away is reported.") },

                            { icon: PhoneOff, text: l("بعّد الموبايل والكتب والورق، ومحدش يكون معاك في الأوضة.", "No phones, books or notes, and nobody else in the room.") },

                            { icon: Wifi, text: l("اتأكد إن النت مستقر، وما تقفلش الصفحة لحد ما الإجابة تتسلّم.", "Use a stable connection and don't close the page until it's submitted.") },

                        ].map(({ icon: Icon, text }) => (

                            <li key={text} className="flex gap-2.5 rounded-xl bg-sheet/70 p-2.5">

                                <Icon className="mt-0.5 size-4 shrink-0 text-sky-600 dark:text-sky-400" aria-hidden />

                                <span>{text}</span>

                            </li>

                        ))}

                    </ul>

                    <p className="mt-3 flex gap-2 text-xs text-ink-3">

                        <Camera className="size-3.5 shrink-0" aria-hidden />

                        {l("هنطلب إذن الكاميرا والميكروفون. السؤال بيظهر لما تضغط «ابدأ الإجابة»، والوقت بيبدأ ساعتها.", "We'll ask for camera and microphone access. The question appears when you press Start answering — the timer starts then.")}

                    </p>

                    <label className="mt-4 flex cursor-pointer items-center gap-2.5 rounded-xl border border-rule bg-sheet px-3 py-2.5 text-sm font-bold text-ink">

                        <input

                            type="checkbox"

                            checked={guideAccepted}

                            onChange={(e) => setGuideAccepted(e.target.checked)}

                            className="size-4 accent-[#6F4E37]"

                        />

                        {l("قريت الإرشادات وجاهز أبدأ", "I've read the tips and I'm ready")}

                    </label>

                </section>



                <Button size="lg" className="mt-6 w-full" onClick={startExam} disabled={!question || !guideAccepted}>

                    <Camera className="size-5" aria-hidden />{l("تشغيل الكاميرا", "Turn on camera")}

                </Button>

                <p className="mt-3 text-center text-xs text-ink-3">{l("السؤال مش هيظهر لسه. هتشوف الكاميرا الأول وتجهّز براحتك.", "The question won't show yet. You'll see your camera first and get settled.")}</p>



                <div className="mt-6 flex justify-center border-t border-rule pt-5">

                    <BreathingCoach className="w-full max-w-sm" />

                </div>

            </div>

            </div>

        </Sheet>

    );



    if (phase === "processing") return (

        <Sheet>

            <div className="text-center" role="status" aria-live="polite">

                <LogoMark size={64} className="mx-auto animate-pulse" />

                <h1 className="mt-6 text-2xl font-bold">{l("بنسلّم إجابتك", "Sending your answer")}</h1>

                <p className="mt-2 text-ink-2">{l("خليك في الصفحة دي لحد ما التسجيل يوصل. التصحيح بيكمل بعدها لوحده.", "Stay on this page until the recording arrives. Grading carries on by itself after that.")}</p>

                <ol className="mx-auto mt-8 max-w-xs space-y-3 text-start text-sm text-ink-2">

                    {[

                        l("رفع التسجيل", "Uploading the recording"),

                        l("حفظ إجابتك", "Saving your answer"),

                        l("إضافتها لطابور التصحيح", "Adding it to the grading queue"),

                    ].map((s, i) => (

                        <li key={s} className="flex items-center gap-3">

                            <span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-rule-strong font-display text-xs tabular">{i + 1}</span>

                            {s}

                        </li>

                    ))}

                </ol>

            </div>

        </Sheet>

    );



    if (phase === "failed") return (

        <Sheet>

            <Panel className="p-6 sm:p-8">

                <div className="mb-5 flex size-12 items-center justify-center rounded-full bg-warn-wash text-warn"><AlertCircle className="size-6" aria-hidden /></div>

                <h1 className="text-2xl font-bold">{l("الإجابة ماتسلّمتش", "Your answer wasn't submitted")}</h1>

                <p className="mt-2 text-ink-2">

                    {l("حصلت مشكلة في الاتصال بالسيرفر. ارجع للوحة التحكم وابدأ الامتحان تاني، أو كلّم المحاضر لو المشكلة اتكررت.",

                        "Something went wrong reaching the server. Go back and start the exam again, or contact your lecturer if it keeps happening.")}

                </p>

                {errorMsg && <p className="mt-4 rounded-[var(--radius-control)] bg-sheet-2 px-3 py-2 text-sm text-ink-3 [overflow-wrap:anywhere]">{errorMsg}</p>}

                {canResend && lastBlobRef.current && (
                    <Button size="lg" className="mt-6 w-full" onClick={() => { setPhase("processing"); submitToBackend(lastBlobRef.current!); }}>
                        {l("ابعت نفس الإجابة تاني", "Send the same answer again")}
                    </Button>
                )}

                <Button size="lg" variant={canResend ? "ghost" : undefined} className={cn(canResend ? "mt-2" : "mt-6", "w-full")} onClick={() => navigate("/dashboard")}>{l("الرجوع للوحة التحكم", "Back to dashboard")}</Button>

            </Panel>

        </Sheet>

    );



    if (phase === "done") {

        const hasNext = currentQIndex + 1 < allQuestions.length;

        const g = studentGradeOf(result?.overall_score);

        const cheer = encouragementOf(result?.overall_score);

        const otherExams = remainingExams.filter((e) => e.exam_token !== examToken);

        return (

            <Sheet wide>

                <Panel className="p-6 text-center sm:p-10">

                    <p className="text-sm text-ink-3">

                        {multi ? l(`سؤال ${currentQIndex + 1} من ${allQuestions.length}`, `Question ${currentQIndex + 1} of ${allQuestions.length}`) : l("الامتحان", "Exam")}

                    </p>

                    <DrawnCheck className="mx-auto mt-3 size-14 text-pass" />

                    <h1 className="mt-3 text-2xl font-bold">{l("إجابتك اتسلّمت", "Your answer is in")}</h1>

                    {grading && grading.status === "completed" && !result && (
                        <p className="mx-auto mt-5 max-w-sm rounded-xl border border-rule bg-sheet-2 px-4 py-3 text-ink-2" role="status">
                            {l("تم تصحيح الإجابة، في انتظار نشر النتائج من المحاضر.", "Your answer has been graded; waiting for your lecturer to publish the results.")}
                        </p>
                    )}

                    {grading && grading.status !== "completed" && (
                        <div className="mx-auto mt-5 max-w-sm" role="status" aria-live="polite">
                            {grading.status === "failed" ? (
                                <Alert tone="warn">
                                    {l("التصحيح الآلي ماكملش. إجابتك محفوظة، والمحاضر يقدر يعيد تصحيحها.", "Automatic grading didn't finish. Your answer is saved and your lecturer can have it graded again.")}
                                </Alert>
                            ) : (
                                <>
                                    <LogoMark size={40} className="mx-auto animate-pulse" />
                                    <p className="mt-3 font-semibold">
                                        {grading.status === "processing"
                                            ? l("جاري تصحيح إجابتك", "Grading your answer")
                                            : grading.attempts > 0
                                                ? l("حصلت مشكلة مؤقتة في التصحيح، وهنعيد المحاولة لوحدنا", "Grading hit a temporary problem; it will be retried automatically")
                                                : l("إجابتك في انتظار التصحيح", "Your answer is waiting to be graded")}
                                    </p>
                                    {grading.status === "queued" && grading.queueAhead != null && grading.queueAhead > 0 && (
                                        <p className="mt-1 text-sm text-ink-2">
                                            {l(`قبلك ${grading.queueAhead} إجابة في الطابور`, `${grading.queueAhead} answers ahead of yours`)}
                                        </p>
                                    )}
                                    <p className="mt-2 text-sm text-ink-3">
                                        {sessionLost
                                            ? t("exam.sessionExpired")
                                            : grading.unreachable
                                                ? l("بنحاول نوصل للسيرفر... إجابتك محفوظة.", "Trying to reach the server... your answer is saved.")
                                                : hasNext
                                                    ? l("تقدر تكمل السؤال اللي بعده دلوقتي؛ النتيجة هتتحفظ لوحدها.", "You can move on to the next question now; the result is saved on its own.")
                                                    : l("تقدر تستنى هنا أو تقفل الصفحة؛ النتيجة هتتحفظ لوحدها.", "You can wait here or close this page; the result is saved on its own.")}
                                    </p>
                                </>
                            )}
                        </div>
                    )}



                    {result && (

                        <>

                            <div className="mt-6 flex flex-col items-center gap-2">

                                <ScoreMark score={result.overall_score} size="xl" animate ink="kind" />

                                {g && <Badge tone={g.tone}>{l(g.ar, g.en)}</Badge>}

                            </div>

                            {cheer && <p className="mx-auto mt-4 max-w-sm text-[1.0625rem] leading-relaxed text-ink-2">{l(cheer.ar, cheer.en)}</p>}

                            <dl className="mt-8 grid grid-cols-3 border-y border-rule py-4">

                                {[

                                    { label: l("المحتوى", "Content"), value: result.nlp_score },

                                    { label: l("الطلاقة", "Fluency"), value: result.speech_score },

                                    { label: l("النزاهة", "Integrity"), value: result.facial_score },

                                ].map((r, i) => (

                                    <div key={r.label} className={cn(i > 0 && "border-s border-rule")}>

                                        <dt className="text-sm text-ink-2">{r.label}</dt>

                                        <dd className="mt-1 font-display text-xl font-semibold tabular">{r.value == null ? "—" : Math.round(r.value)}</dd>

                                    </div>

                                ))}

                            </dl>

                            <p className="mt-3 text-xs text-ink-3">{l("الدرجة = 80% محتوى + 10% طلاقة + 10% نزاهة. الدرجة النهائية بتظهر في «درجاتي» بعد مراجعة المحاضر.", "Grade = 80% content + 10% fluency + 10% integrity. The final grade appears in My grades after your lecturer reviews it.")}</p>



                            {result.transcript && (

                                <details className="mt-6 text-start">

                                    <summary className="cursor-pointer text-sm font-semibold text-pen">{l("إجابتك كما سمعناها", "Your answer as we heard it")}</summary>

                                    <blockquote className="mt-3 border-s-[3px] border-pen/50 bg-sheet-2 px-4 py-3 leading-loose" dir="auto">{result.transcript}</blockquote>

                                </details>

                            )}

                        </>

                    )}



                    <div className="mt-8 flex flex-col gap-2">

                        {hasNext ? (

                            <Button size="lg" onClick={goToNextQuestion}>

                                {l(`السؤال التالي (${allQuestions.length - currentQIndex - 1} متبقي)`, `Next question (${allQuestions.length - currentQIndex - 1} left)`)}

                            </Button>

                        ) : otherExams.length > 0 ? (

                            <>

                                <Button size="lg" onClick={() => { forgetPendingGrading(); goToNextExam(); }}>{l("الامتحان التالي", "Next exam")}</Button>

                                <Button variant="ghost" onClick={() => { forgetPendingGrading(); navigate("/dashboard"); }}>{l("الرجوع للوحة التحكم", "Back to dashboard")}</Button>

                            </>

                        ) : (

                            <Button size="lg" onClick={() => { forgetPendingGrading(); navigate("/dashboard"); }}>{l("الرجوع للوحة التحكم", "Back to dashboard")}</Button>

                        )}

                    </div>

                </Panel>

            </Sheet>

        );

    }



    // ═══════════════════════════════════════════════════════════════════════════

    //  Main exam screen: preview + recording

    //  (video element is always mounted here so the ref is always valid)

    // ═══════════════════════════════════════════════════════════════════════════

    const recording = phase === "recording";

    const activeAlerts = import.meta.env.DEV

        ? (["gaze_left", "gaze_right", "gaze_up", "gaze_down", "no_face", "face_mismatch", "phone_detected", "book_detected"] as const)

            .map((k) => [k, antiCheatAlertsRef.current[k] || 0] as const).filter(([, v]) => v > 0)

        : [];



    return (

        <div className="relative isolate flex min-h-dvh flex-col bg-paper">

            <CalmBackdrop />

            {/* Sticky bar over scrolling content. avoid-ai-design-ignore: K3 */}

            <header className="sticky top-0 z-20 border-b border-rule bg-sheet/90 backdrop-blur">

                <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">

                    <LogoMark size={26} className="sm:hidden" />

                    <Logo height={20} className="max-sm:hidden" title="OralIQ" />

                    {multi && (

                        <ol className="flex items-center gap-1.5" aria-label={l(`سؤال ${currentQIndex + 1} من ${allQuestions.length}`, `Question ${currentQIndex + 1} of ${allQuestions.length}`)}>

                            {allQuestions.map((q, i) => (

                                <li key={q.id} aria-current={i === currentQIndex ? "step" : undefined}

                                    className={cn("h-1.5 rounded-full transition-all", i === currentQIndex ? "w-6 bg-pen" : i < currentQIndex ? "w-3 bg-pen/40" : "w-3 bg-rule-strong")} />

                            ))}

                        </ol>

                    )}

                    <div className="ms-auto flex items-center gap-4">

                        {recording ? (

                            <span role="timer" aria-live="off" className={cn("flex items-center gap-2 font-display text-xl font-semibold tabular ltr", lowTime ? "text-sun" : "text-ink")}>

                                <span className="relative flex size-2.5">

                                    <span className="absolute inset-0 rounded-full bg-mark motion-safe:animate-[oiq-pulse-ring_1.4s_ease-out_infinite]" />

                                    <span className="relative size-2.5 rounded-full bg-mark" />

                                </span>

                                {mmss(timeLeft)}

                            </span>

                        ) : (

                            <span className="text-sm text-ink-2">{question ? `${l("الوقت", "Time")}: ${countOf(lang, Math.round(question.timeLimit / 60), NOUNS.minute)}` : null}</span>

                        )}

                        <span className="hidden max-w-40 truncate text-sm text-ink-3 md:inline">{studentName}</span>

                    </div>

                </div>

                {recording && (

                    <div className="h-1 bg-rule" aria-hidden>

                        <div className={cn("h-full transition-[width] duration-1000 ease-linear", lowTime ? "bg-sun" : "bg-pen")} style={{ width: `${Math.min(100, progress * 100)}%` }} />

                    </div>

                )}

            </header>



            <main className="mx-auto grid w-full max-w-6xl flex-1 content-start gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)] lg:gap-10 lg:py-10">

                {/* ── Camera ── */}

                <section className="lg:order-2" aria-label={l("الكاميرا", "Camera")}>

                    <div className={cn(

                        "relative mx-auto aspect-square w-full overflow-hidden rounded-[var(--radius-panel)] bg-black ring-2 transition-[max-width] duration-300",

                        // On phones, shrink the camera while answering so the question fits on screen —

                        // scrolling down to read it would itself register as looking down.

                        recording ? "max-w-[min(420px,55vw)] lg:max-w-[420px]" : "max-w-[420px]",

                        liveAlert ? "ring-warn" : "ring-rule",

                    )}>

                        <video ref={videoRef} muted playsInline className={cn("size-full -scale-x-100 object-cover", !stream && "hidden")} />

                        <canvas ref={canvasRef} width={440} height={440} className="pointer-events-none absolute inset-0 size-full -scale-x-100" />



                        {!stream && <div className="flex size-full items-center justify-center text-ink-3"><Camera className="size-10" aria-hidden /></div>}



                        {/* Framing guide while calibrating */}

                        {phase === "preview" && stream && (

                            <div className="pointer-events-none absolute inset-0 flex items-center justify-center" aria-hidden>

                                <div className="h-[62%] w-[46%] rounded-[50%] border-2 border-dashed border-white/70" />

                            </div>

                        )}



                        {recording && (

                            <span className="absolute start-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-mark px-2.5 py-1 text-xs font-bold text-white">

                                <span className="size-1.5 rounded-full bg-white motion-safe:animate-pulse" />{l("تسجيل", "REC")}

                            </span>

                        )}



                        <div aria-live="assertive" className="absolute inset-x-3 bottom-3 flex justify-center">

                            {liveAlert && (

                                <span className="flex items-center gap-2 rounded-full bg-sheet px-4 py-2 text-sm font-semibold text-warn shadow-pop animate-[oiq-pop-in_160ms_ease-out]">

                                    <span className="size-2 rounded-full bg-warn" aria-hidden />

                                    {alertText(liveAlert)}

                                </span>

                            )}

                        </div>

                    </div>

                    <p className="mx-auto mt-3 max-w-[420px] text-center text-sm text-ink-3">

                        {phase === "preview"

                            ? l("خلي وشك جوه الدائرة وبص للشاشة.", "Keep your face inside the oval and look at the screen.")

                            : l("الكاميرا بتتأكد إن انت اللي بتجاوب.", "The camera confirms it's you answering.")}

                    </p>

                    {activeAlerts.length > 0 && (

                        <p className="mx-auto mt-2 flex max-w-[420px] flex-wrap justify-center gap-1.5 text-xs text-ink-3 ltr" title="DEV only">

                            {activeAlerts.map(([k, v]) => <span key={k} className="rounded bg-sheet-2 px-1.5 py-0.5">{k.replace("gaze_", "")} {v.toFixed(1)}s</span>)}

                        </p>

                    )}

                </section>



                {/* ── Question sheet ── */}

                <section className="lg:order-1">

                    <Panel className="overflow-hidden">

                        <div className="flex items-center justify-between gap-3 border-b border-rule px-5 py-3 text-sm text-ink-2 sm:px-7">

                            <span>{multi ? l(`سؤال ${currentQIndex + 1} من ${allQuestions.length}`, `Question ${currentQIndex + 1} of ${allQuestions.length}`) : l("السؤال", "Question")}</span>

                            {question && <span className="tabular">{countOf(lang, Math.round(question.timeLimit / 60), NOUNS.minute)}</span>}

                        </div>



                        <div

                            className="min-h-52 px-5 py-8 sm:px-7"

                            // Ruled like an answer booklet; rule spacing = the heading's 3rem line height

                            style={recording ? { backgroundImage: "repeating-linear-gradient(to bottom, transparent 0, transparent calc(3rem - 1px), var(--rule) calc(3rem - 1px), var(--rule) 3rem)", backgroundPositionY: "2rem" } : undefined}

                        >

                            {recording && question ? (

                                <h1 className="text-[1.375rem] font-semibold leading-[3rem] sm:text-[1.75rem]" dir="auto">{question.text}</h1>

                            ) : (

                                <div>

                                    <h1 className="text-xl font-semibold">{l("خد راحتك، السؤال لسه مظهرش", "Take your time, the question isn't showing yet")}</h1>

                                    <p className="mt-2 text-ink-2">

                                        {l("ظبّط قعدتك والإضاءة. لما تحس إنك جاهز اضغط «ابدأ الإجابة»، وساعتها السؤال هيظهر والوقت هيبدأ.",

                                            "Get comfortable and check your lighting. When you feel ready, press Start answering: the question appears and the timer starts then.")}

                                    </p>

                                    <p className="mt-3 text-sm text-ink-3">

                                        {l("نصيحة: فكّر ثانيتين قبل ما تتكلم، ده طبيعي وماحدش بيحسبه عليك.", "Tip: pausing a moment to think before you speak is normal. Nobody holds it against you.")}

                                    </p>

                                </div>

                            )}

                        </div>



                        <div className="border-t border-rule px-5 py-4 sm:px-7">

                            <div className="flex items-center gap-3">

                                <Mic className={cn("size-5 shrink-0", recording ? "text-pen" : "text-ink-3")} aria-hidden />

                                <LiveWaveform stream={stream} active={recording} label={l("مستوى صوت الميكروفون", "Microphone level")} />

                            </div>

                            <p className="mt-1 text-xs text-ink-3">

                                {recording

                                    ? l("لو الخطوط مش بتتحرك وانت بتتكلم، قرّب من الميكروفون.", "If the bars don't move while you speak, get closer to the mic.")

                                    : l("صوتك هيتسجّل بس بعد ما تبدأ الإجابة.", "Your voice is only recorded once you start answering.")}

                            </p>

                        </div>

                    </Panel>



                    {errorMsg && <Alert tone="error" className="mt-4">{errorMsg}</Alert>}



                    <div className="sticky bottom-4 mt-6 lg:static">

                        {phase === "preview" && (

                            <Button size="lg" className="h-14 w-full text-lg shadow-pop lg:shadow-none" onClick={startRecording}>

                                <Mic className="size-5" aria-hidden />{l("ابدأ الإجابة", "Start answering")}

                            </Button>

                        )}

                        {recording && (

                            <Button size="lg" className="h-14 w-full bg-ink text-lg text-paper shadow-pop hover:bg-ink/90 lg:shadow-none" onClick={stopAndSubmit}>

                                <Square className="size-4 fill-current" aria-hidden />{l("خلصت، سلّم الإجابة", "I'm done — submit")}

                            </Button>

                        )}

                    </div>

                </section>

            </main>

        </div>

    );

}



/** Centered single-sheet layout for the non-camera phases (module-level so inputs keep focus). */

function Sheet({ children, wide = false, size }: { children: React.ReactNode; wide?: boolean; size?: "xl" }) {

    return (

        <div className="relative isolate flex min-h-dvh flex-col bg-paper">

            <CalmBackdrop />

            <header className="flex h-16 items-center justify-between px-5 sm:px-8">

                <Logo height={22} title="OralIQ" />

                <div className="flex items-center gap-1"><LanguageToggle compact /><ThemeToggle /></div>

            </header>

            <main className={cn("mx-auto flex w-full flex-1 flex-col justify-center px-4 pb-16", size === "xl" ? "max-w-4xl" : wide ? "max-w-xl" : "max-w-md")}>

                {children}

            </main>

        </div>

    );

}



/** Soft, still light behind the exam screens: warmer than a blank page, never moving. */

function CalmBackdrop() {

    return (

        <div

            className="pointer-events-none fixed inset-0 -z-10"

            style={{

                backgroundImage:

                    "radial-gradient(40% 45% at 85% 5%, color-mix(in oklab, var(--pen) 9%, transparent), transparent 70%), radial-gradient(35% 40% at 5% 95%, color-mix(in oklab, var(--sun) 9%, transparent), transparent 70%), radial-gradient(30% 35% at 10% 10%, color-mix(in oklab, var(--teal) 6%, transparent), transparent 70%)",

            }}

            aria-hidden

        />

    );

}