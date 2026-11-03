import { useState, useRef } from "react";
import { Mic, Square } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { cn } from "../lib/utils";
import { buttonClasses } from "./ui/button";

interface VoiceRecordButtonProps {
    onTranscribed: (text: string) => void;
    hint?: string;
    label?: string;
    disabled?: boolean;
}

/** Dictate into a text field: record → Whisper → append text. */
export default function VoiceRecordButton({ onTranscribed, hint = "", label, disabled }: VoiceRecordButtonProps) {
    const { l } = useI18n();
    const [recording, setRecording] = useState(false);
    const [processing, setProcessing] = useState(false);
    const [error, setError] = useState("");
    const recorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);

    const startRecording = async () => {
        setError("");
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
            });
            chunksRef.current = [];
            const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
            const rec = new MediaRecorder(stream, { mimeType: mime });
            rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
            rec.onstop = async () => {
                stream.getTracks().forEach((t) => t.stop());
                const blob = new Blob(chunksRef.current, { type: "audio/webm" });
                if (blob.size < 500) {
                    setError(l("التسجيل قصير جداً. اتكلم أكتر وجرّب تاني.", "Too short. Speak a little longer and try again."));
                    return;
                }
                setProcessing(true);
                try {
                    const fd = new FormData();
                    fd.append("audio", blob, "dictation.webm");
                    if (hint) fd.append("hint", hint);
                    const { data } = await api.post("/speech/transcribe", fd, {
                        headers: { "Content-Type": "multipart/form-data" },
                        timeout: 120_000,
                    });
                    if (data?.text) onTranscribed(data.text);
                    else setError(l("ملقيناش كلام في التسجيل.", "No speech was found in the recording."));
                } catch (e: unknown) {
                    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                    setError(detail || l("تعذّر تحويل الصوت لنص. اكتب بدلاً من ذلك.", "Couldn't transcribe. Type it instead."));
                } finally {
                    setProcessing(false);
                }
            };
            recorderRef.current = rec;
            rec.start(100);
            setRecording(true);
        } catch {
            setError(l("اسمح للمتصفح باستخدام الميكروفون.", "Allow the browser to use your microphone."));
        }
    };

    const stopRecording = () => {
        if (recorderRef.current?.state === "recording") recorderRef.current.stop();
        setRecording(false);
    };

    return (
        <span className="inline-flex flex-col items-end gap-1">
            <button
                type="button"
                onClick={recording ? stopRecording : startRecording}
                disabled={disabled || processing}
                aria-pressed={recording}
                className={cn(
                    buttonClasses("ghost", "sm", "h-8 px-2.5 text-[0.8125rem]"),
                    recording && "bg-mark-wash text-mark hover:bg-mark-wash hover:text-mark",
                )}
            >
                {processing ? (
                    <><span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />{l("جاري الكتابة…", "Transcribing…")}</>
                ) : recording ? (
                    <><Square className="size-3.5 fill-current" aria-hidden />{l("إيقاف التسجيل", "Stop")}</>
                ) : (
                    <><Mic className="size-4" aria-hidden />{label ?? l("املِ بصوتك", "Dictate")}</>
                )}
            </button>
            {error && <span role="alert" className="text-xs text-mark">{error}</span>}
        </span>
    );
}
