/** Shapes returned by the OralIQ API (see backend/app/schemas). */

export interface Me {
    id: number;
    email: string;
    full_name: string;
    role: "student" | "lecturer" | "hr" | "admin" | string;
    is_active: boolean;
}

export const isLecturerRole = (role?: string | null) => !!role && ["lecturer", "hr", "admin"].includes(role);

export interface Question {
    id: number;
    text: string;
    model_answer: string;
    keywords: string;
    difficulty: string;
    category: string;
    duration_minutes: number;
    /** Attempts per student at this question's exam (enforced by the server per sitting). */
    max_attempts?: number;
    /** manual: hidden until the lecturer publishes; immediate: shown once graded (whole exam). */
    results_policy?: "manual" | "immediate";
    results_published_at?: string | null;
    exam_token: string;
    group_token: string | null;
    order_index: number;
    creator_id: number | null;
    created_at: string | null;
}

export interface Submission {
    id: number;
    question_id: number;
    student_name: string;
    student_number: string;
    transcript: string | null;
    nlp_score: number | null;
    facial_score: number | null;
    speech_score: number | null;
    voice_score: number | null;
    face_score: number | null;
    overall_score: number | null;
    cheat_report: string | null;
    fluency_report: string | null;
    grade_visible: number;
    started_at: string | null;
    finished_at: string | null;
    submitted_at: string | null;
    question_text: string | null;
    question_category: string | null;
    lecturer_name?: string | null;
    /** queued | processing | completed | failed — scores are empty until "completed". */
    grading_status?: "queued" | "processing" | "completed" | "failed";
    /** Server face checks behind face_score; null on answers graded before they were recorded. */
    face_verification?: "verified" | "uncertain" | "mismatch" | "no_face" | "unverified" | "not_enrolled" | null;
    face_checks?: number | null;
    /** server_sampled: facial_score measured from server face checks; insufficient_data: not measured. */
    integrity_status?: "server_sampled" | "insufficient_data" | null;
    /** What the student's browser reported (JSON) — indicators only, never evidence. */
    client_alerts?: string | null;
    /** Whether the grade may be shown to its student; for a student it is null-blanked until then. */
    result_visible?: boolean | null;
}

export interface Assignment {
    id: number;
    question_id: number;
    assigned_at: string | null;
    status: string;
    question_text: string | null;
    question_category: string | null;
    question_difficulty: string | null;
    exam_token: string | null;
    assigned_by_name: string | null;
}

export interface StudentRow {
    id: number;
    full_name: string;
    email: string;
    has_voiceprint: boolean;
    has_faceprint: boolean;
    voice_locked: boolean;
    face_locked: boolean;
    voice_reenroll_allowed: boolean;
}

export interface BiometricStatus {
    has_voiceprint: boolean;
    has_faceprint: boolean;
    biometrics_complete: boolean;
    voice_locked: boolean;
    face_locked: boolean;
    voice_reenroll_allowed: boolean;
    can_reenroll: boolean;
}

/** Integrity needs a human look: severe proctoring events or identity not confirmed. */
export function needsReview(s: Pick<Submission, "facial_score" | "cheat_report">): boolean {
    if (s.facial_score != null && s.facial_score < 70) return true;
    return !!s.cheat_report && s.cheat_report.includes("NOT VERIFIED");
}

/** Student-facing exam title: subject name, never the question text (it must stay hidden until the exam starts). */
export function examTitleOf(a: { question_category?: string | null }, l: (ar: string, en: string) => string): string {
    const c = (a.question_category || "").trim();
    return c && c.toLowerCase() !== "general" ? l(`امتحان مادة ${c}`, `${c} exam`) : l("امتحان شفوي", "Oral exam");
}
