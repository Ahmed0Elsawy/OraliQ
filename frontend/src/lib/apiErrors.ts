/** Turn axios/FastAPI errors into a clear message in the user's language. */

const isArabic = () => {
    try { return localStorage.getItem("oraliq_lang") !== "en"; } catch { return true; }
};

/** Backend `detail` strings (English) the user can actually hit, translated. */
const KNOWN_DETAILS: Record<string, { ar: string; en: string }> = {
    "Lecturers only": { ar: "الصفحة دي للمحاضرين بس.", en: "This page is for lecturers only." },
    "Only lecturers can create questions": { ar: "المحاضرين بس يقدروا يضيفوا أسئلة.", en: "Only lecturers can add questions." },
    "Question not found": { ar: "السؤال ده مش موجود أو اتحذف.", en: "This question doesn't exist or was deleted." },
    "Exam not found": { ar: "الامتحان ده مش موجود. اطلب من المحاضر الرابط تاني.", en: "This exam doesn't exist. Ask your lecturer for the link again." },
    "Exam group not found": { ar: "الامتحان ده مش موجود. اطلب من المحاضر الرابط تاني.", en: "This exam doesn't exist. Ask your lecturer for the link again." },
    "Not your question": { ar: "مش هينفع تعدّل سؤال محاضر تاني.", en: "You can't change another lecturer's question." },
    "Student not found": { ar: "الطالب ده مش موجود.", en: "That student doesn't exist." },
    "Submission not found": { ar: "الإجابة دي مش موجودة.", en: "That answer doesn't exist." },
    "Incorrect email or password": { ar: "البريد أو كلمة المرور غير صحيحة.", en: "That email and password don't match." },
    "Inactive user": { ar: "الحساب ده متوقف. كلّم مسؤول المنصة.", en: "This account is disabled. Contact your platform admin." },
    "Audio file is required": { ar: "مفيش تسجيل صوتي.", en: "No audio recording was sent." },
    "Could not detect speech in recording": { ar: "ملقيناش كلام في التسجيل.", en: "No speech was found in the recording." },
    "Recording too short — speak longer": { ar: "التسجيل قصير جداً. اتكلم أكتر.", en: "The recording is too short. Speak a little longer." },
    "Student has no biometrics enrolled yet": { ar: "الطالب لسه ماسجلش وشه وصوته.", en: "This student hasn't registered face and voice yet." },
};

export function getApiErrorMessage(err: unknown, fallback?: string): string {
    const ar = isArabic();
    const t = (a: string, e: string) => (ar ? a : e);
    const e = err as { response?: { status?: number; data?: { detail?: unknown } }; code?: string; message?: string };
    const detail = e?.response?.data?.detail;
    const status = e?.response?.status;

    // No response at all: offline, DNS, CORS, or timeout
    if (!e?.response) {
        if (e?.code === "ECONNABORTED") return t("السيرفر اتأخر في الرد. جرّب تاني بعد لحظات.", "The server took too long to answer. Try again shortly.");
        return t("تعذّر الوصول للسيرفر. اتأكد من الإنترنت وجرّب تاني.", "Couldn't reach the server. Check your connection and try again.");
    }

    if (typeof detail === "string") {
        const known = KNOWN_DETAILS[detail];
        if (known) return ar ? known.ar : known.en;
        // Backend Arabic messages are already user-facing; keep them.
        if (/[؀-ۿ]/.test(detail)) return detail;
    }

    // Plan-limit errors (HTTP 402) carry a bilingual object: { code, message, message_en, upgrade_required }
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
        const d = detail as { message?: string; message_en?: string };
        const msg = ar ? d.message : (d.message_en || d.message);
        if (msg) return msg;
    }

    if (status === 401 || status === 403) return t("انتهت الجلسة. سجّل الدخول مرة تانية.", "Your session ended. Please sign in again.");
    if (status === 404) return t("المطلوب مش موجود. حدّث الصفحة وجرّب تاني.", "That wasn't found. Refresh the page and try again.");
    if (status === 413) return t("الملف كبير جداً.", "That file is too large.");
    if (status === 422) return t("في بيانات ناقصة أو مش صحيحة. راجعها وجرّب تاني.", "Some details are missing or invalid. Check them and try again.");
    if (status === 429) return t("طلبات كتير في وقت قصير. استنى دقيقة وجرّب تاني.", "Too many requests. Wait a minute and try again.");
    if (status && status >= 500) return t("حصلت مشكلة في السيرفر. جرّب بعد دقيقة.", "Something went wrong on the server. Try again in a minute.");

    return fallback || t("حصل خطأ غير متوقع.", "Something unexpected went wrong.");
}
