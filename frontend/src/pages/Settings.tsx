import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Lock, Mic, ScanFace } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { useTheme, type ThemePref } from "../lib/theme";
import VoiceEnrollmentModal from "../components/VoiceEnrollmentModal";
import { Panel, PanelHeader, PageHeader } from "../components/ui/panel";
import { Alert, Segmented, Skeleton } from "../components/ui/feedback";
import { Avatar } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { isLecturerRole, type BiometricStatus, type Me } from "../lib/types";

// Any reasonable photo is accepted; it's resized + compressed in the browser before saving.
const MAX_PHOTO_BYTES = 25 * 1024 * 1024;
const AVATAR_SIZE = 384;

/** Center-crop to a square, resize to AVATAR_SIZE and encode as compact JPEG (~20–60 KB). */
function compressAvatar(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
            URL.revokeObjectURL(url);
            const side = Math.min(img.naturalWidth, img.naturalHeight);
            if (!side) return reject(new Error("empty image"));
            const sx = (img.naturalWidth - side) / 2;
            const sy = (img.naturalHeight - side) / 2;
            const out = Math.min(AVATAR_SIZE, side);
            const canvas = document.createElement("canvas");
            canvas.width = out;
            canvas.height = out;
            const ctx = canvas.getContext("2d");
            if (!ctx) return reject(new Error("no canvas"));
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, out, out);
            ctx.imageSmoothingQuality = "high";
            ctx.drawImage(img, sx, sy, side, side, 0, 0, out, out);
            resolve(canvas.toDataURL("image/jpeg", 0.85));
        };
        img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("bad image")); };
        img.src = url;
    });
}

export default function Settings() {
    const { l, lang, setLang } = useI18n();
    const { pref, setPref } = useTheme();
    const navigate = useNavigate();
    const [user, setUser] = useState<Me | null>(null);
    const [bio, setBio] = useState<BiometricStatus | null>(null);
    const [profilePic, setProfilePic] = useState<string | null>(null);
    const [photoError, setPhotoError] = useState("");
    const [showEnroll, setShowEnroll] = useState(false);
    const [justEnrolled, setJustEnrolled] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const loadBio = () => api.get("/voice/status").then((r) => setBio(r.data)).catch(() => setBio(null));

    useEffect(() => {
        api.get("/users/me").then((res) => {
            setUser(res.data);
            try {
                const pic = localStorage.getItem(`profilePic_${res.data.email}`);
                if (pic) setProfilePic(pic);
            } catch { /* ignore */ }
        }).catch(() => {});
        loadBio();
    }, []);

    const handlePicChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = "";
        if (!file || !user) return;
        setPhotoError("");
        if (file.size > MAX_PHOTO_BYTES) {
            setPhotoError(l("الصورة كبيرة جداً. اختار صورة أقل من 25 ميجا.", "That photo is too large. Choose one under 25 MB."));
            return;
        }
        compressAvatar(file)
            .then((result) => {
                try {
                    localStorage.setItem(`profilePic_${user.email}`, result);
                    setProfilePic(result);
                } catch {
                    setPhotoError(l("مساحة المتصفح مش كفاية للصورة دي. جرّب صورة تانية.", "Not enough browser storage for that photo. Try another one."));
                }
            })
            .catch(() => {
                setPhotoError(l("مقدرناش نقرأ الصورة دي. جرّب صورة JPG أو PNG.", "Couldn't read that image. Try a JPG or PNG."));
            });
    };

    const removePic = () => {
        if (!user) return;
        try { localStorage.removeItem(`profilePic_${user.email}`); } catch { /* ignore */ }
        setProfilePic(null);
    };

    const lecturer = isLecturerRole(user?.role);
    let pendingExam = false;
    try { pendingExam = !!localStorage.getItem("pendingExamToken"); } catch { /* ignore */ }

    return (
        <div className="max-w-4xl">
            <PageHeader title={l("الإعدادات", "Settings")} description={l("حسابك، وهويتك في الامتحانات، وشكل المنصة.", "Your account, exam identity and how OralIQ looks.")} />

            <div className="space-y-6">
                {/* ── Account ── */}
                <Panel>
                    <PanelHeader title={l("الحساب", "Account")} />
                    <div className="flex flex-col gap-6 p-6 sm:flex-row sm:items-start">
                        <div className="flex items-center gap-4 sm:flex-col sm:items-center">
                            <Avatar name={user?.full_name} src={profilePic} size="lg" className="size-20 text-2xl" />
                            <div className="flex flex-col gap-2 sm:items-center">
                                <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()}>
                                    {profilePic ? l("تغيير الصورة", "Change photo") : l("إضافة صورة", "Add photo")}
                                </Button>
                                {profilePic && <Button variant="ghost" size="sm" onClick={removePic}>{l("إزالة", "Remove")}</Button>}
                                <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handlePicChange} />
                            </div>
                        </div>
                        <dl className="grid flex-1 gap-4 sm:grid-cols-2">
                            {user ? (
                                <>
                                    <div className="rounded-xl border border-rule bg-sheet-2/60 p-3.5">
                                        <dt className="text-xs font-extrabold uppercase tracking-wider text-ink-2">{l("الاسم", "Name")}</dt>
                                        <dd className="mt-1 text-base font-extrabold text-ink">{user.full_name}</dd>
                                    </div>
                                    <div className="rounded-xl border border-rule bg-sheet-2/60 p-3.5">
                                        <dt className="text-xs font-extrabold uppercase tracking-wider text-ink-2">{l("البريد الإلكتروني", "Email")}</dt>
                                        <dd className="mt-1 text-base font-extrabold text-ink ltr">{user.email}</dd>
                                    </div>
                                    <div className="rounded-xl border border-rule bg-sheet-2/60 p-3.5 sm:col-span-2">
                                        <dt className="text-xs font-extrabold uppercase tracking-wider text-ink-2">{l("نوع الحساب", "Account type")}</dt>
                                        <dd className="mt-1 text-base font-extrabold text-ink">{lecturer ? l("محاضر", "Lecturer") : l("طالب", "Student")}</dd>
                                    </div>
                                </>
                            ) : (
                                <><Skeleton className="h-14 w-full" /><Skeleton className="h-14 w-full" /></>
                            )}
                        </dl>
                    </div>
                    {photoError && <Alert tone="error" className="mx-6 mb-5">{photoError}</Alert>}
                    <p className="border-t border-rule px-6 py-3.5 text-sm font-semibold text-ink-2">
                        {l("الصورة بتتحفظ على الجهاز ده بس. لتعديل الاسم أو البريد أو كلمة المرور، كلّم مسؤول المنصة.",
                            "Your photo is saved on this device only. To change your name, email or password, contact your platform admin.")}
                    </p>
                </Panel>

                {/* ── Identity ── */}
                {!lecturer && (
                    <Panel>
                        <PanelHeader
                            title={l("هويتك في الامتحانات", "Exam identity")}
                            description={l("وشك وصوتك بيتقارنوا أثناء كل امتحان للتأكد إنك انت اللي بتجاوب.", "Your face and voice are checked during every exam to confirm it's you.")}
                        />
                        <ul className="divide-y divide-rule">
                            {[
                                { icon: ScanFace, label: l("الوجه", "Face"), ok: bio?.has_faceprint },
                                { icon: Mic, label: l("الصوت", "Voice"), ok: bio?.has_voiceprint },
                            ].map(({ icon: Icon, label, ok }) => (
                                <li key={label} className="flex items-center gap-3.5 px-6 py-4">
                                    <Icon className="size-5 text-ink" aria-hidden />
                                    <span className="flex-1 text-base font-extrabold text-ink">{label}</span>
                                    {bio == null ? <Skeleton className="h-6 w-20" /> : ok ? <Badge tone="pass">{l("مسجّل", "Registered")}</Badge> : <Badge tone="warn">{l("غير مسجّل", "Not registered")}</Badge>}
                                </li>
                            ))}
                        </ul>
                        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule px-6 py-4">
                            {bio && !bio.biometrics_complete ? (
                                <>
                                    <p className="text-sm font-bold text-ink-2">{l("لازم تسجّلهم قبل أول امتحان. بياخد حوالي دقيقتين.", "Required before your first exam. Takes about two minutes.")}</p>
                                    <Button size="lg" onClick={() => setShowEnroll(true)}>{l("سجّل الآن", "Register now")}</Button>
                                </>
                            ) : bio?.can_reenroll ? (
                                <>
                                    <p className="text-sm font-bold text-ink-2">{l("المحاضر سمحلك تعيد التسجيل.", "Your lecturer allowed you to register again.")}</p>
                                    <Button variant="secondary" size="lg" onClick={() => setShowEnroll(true)}>{l("إعادة التسجيل", "Register again")}</Button>
                                </>
                            ) : bio ? (
                                <p className="flex items-center gap-2 text-sm font-bold text-ink-2">
                                    <Lock className="size-4 text-ink" aria-hidden />
                                    {l("مقفول لحماية الامتحانات. لو محتاج تغيّره، اطلب من المحاضر يسمحلك.", "Locked to protect exams. Ask your lecturer if you need to change it.")}
                                </p>
                            ) : null}
                        </div>
                        {justEnrolled && pendingExam && (
                            <Alert tone="success" className="mx-6 mb-5" title={l("تمام، هويتك اتسجلت", "Done — your identity is registered")}
                                action={<Button size="sm" onClick={() => navigate("/exam/start")}>{l("كمّل الامتحان", "Continue to exam")}</Button>}>
                                {l("عندك امتحان مستنيك.", "You have an exam waiting.")}
                            </Alert>
                        )}
                    </Panel>
                )}

                {/* ── Appearance ── */}
                <Panel>
                    <PanelHeader title={l("المظهر واللغة", "Appearance and language")} />
                    <div className="grid gap-6 p-6 sm:grid-cols-2">
                        <div className="flex flex-col gap-2.5">
                            <span className="text-base font-extrabold text-ink">{l("الوضع", "Theme")}</span>
                            <Segmented<ThemePref>
                                label={l("الوضع", "Theme")}
                                className="self-start"
                                value={pref}
                                onChange={setPref}
                                options={[
                                    { value: "system", label: l("حسب الجهاز", "System") },
                                    { value: "light", label: l("نهاري", "Light") },
                                    { value: "dark", label: l("ليلي", "Dark") },
                                ]}
                            />
                        </div>
                        <div className="flex flex-col gap-2.5">
                            <span className="text-base font-extrabold text-ink">{l("اللغة", "Language")}</span>
                            <Segmented
                                label={l("اللغة", "Language")}
                                className="self-start"
                                value={lang}
                                onChange={setLang}
                                options={[{ value: "ar", label: "العربية" }, { value: "en", label: "English" }]}
                            />
                        </div>
                    </div>
                </Panel>
            </div>

            <VoiceEnrollmentModal
                isOpen={showEnroll}
                onClose={() => setShowEnroll(false)}
                onSuccess={() => { setShowEnroll(false); setJustEnrolled(true); loadBio(); }}
            />
        </div>
    );
}
