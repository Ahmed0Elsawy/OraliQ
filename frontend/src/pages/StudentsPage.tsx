import { useCallback, useEffect, useMemo, useState } from "react";
import { Lock, LockOpen, Mic, ScanFace, Search, ShieldCheck, UserX, Users } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { cn } from "../lib/utils";
import { Panel, PageHeader, StatStrip } from "../components/ui/panel";
import { Alert, EmptyState, ListSkeleton, LoadFailed, Segmented } from "../components/ui/feedback";
import { Avatar } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { formatScore } from "../lib/grades";
import { countOf, NOUNS } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiErrors";
import type { StudentRow, Submission } from "../lib/types";
import { useToast } from "../components/ui/toast";

type Filter = "all" | "missing" | "unlocked";

export default function StudentsPage() {
    const { l, lang } = useI18n();
    const toast = useToast();
    const [students, setStudents] = useState<StudentRow[]>([]);
    const [subs, setSubs] = useState<Submission[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [error, setError] = useState("");
    const [query, setQuery] = useState("");
    const [filter, setFilter] = useState<Filter>("all");
    const [busy, setBusy] = useState<number | null>(null);

    const load = useCallback(() => {
        setLoading(true);
        setLoadError("");
        Promise.all([api.get("/exams/students"), api.get("/exams/all-results").catch(() => ({ data: [] }))])
            .then(([s, r]) => { setStudents(s.data); setSubs(r.data); })
            .catch((err) => setLoadError(getApiErrorMessage(err, l("تعذّر تحميل الطلاب.", "Couldn't load students."))))
            .finally(() => setLoading(false));
    }, [l]);
    useEffect(() => { load(); }, [load]);
    const hasData = !loading && !loadError && students.length > 0;

    const statsByName = useMemo(() => {
        const m = new Map<string, number[]>();
        for (const s of subs) {
            const key = (s.student_name || "").trim();
            if (!m.has(key)) m.set(key, []);
            if (s.overall_score != null) m.get(key)!.push(s.overall_score);
        }
        return m;
    }, [subs]);

    const ready = students.filter((s) => s.has_faceprint && s.has_voiceprint).length;

    const visible = students.filter((s) => {
        if (filter === "missing" && s.has_faceprint && s.has_voiceprint) return false;
        if (filter === "unlocked" && !s.voice_reenroll_allowed) return false;
        const q = query.trim().toLowerCase();
        return !q || s.full_name.toLowerCase().includes(q) || s.email.toLowerCase().includes(q);
    });

    const toggleReenroll = async (s: StudentRow) => {
        setBusy(s.id);
        setError("");
        try {
            await api.post(`/voice/${s.voice_reenroll_allowed ? "revoke" : "allow"}-reenroll/${s.id}`);
            setStudents((prev) => prev.map((x) => (x.id === s.id ? { ...x, voice_reenroll_allowed: !s.voice_reenroll_allowed } : x)));
            toast(s.voice_reenroll_allowed
                ? l(`اتلغى إذن ${s.full_name}`, `Permission revoked for ${s.full_name}`)
                : l(`${s.full_name} يقدر يعيد تسجيل هويته دلوقتي`, `${s.full_name} can now re-register`));
        } catch (err) {
            setError(getApiErrorMessage(err, l("تعذّر تغيير الإذن.", "Couldn't change the permission.")));
        } finally {
            setBusy(null);
        }
    };

    return (
        <>
            <PageHeader
                title={l("الطلاب", "Students")}
                description={l("كل الطلاب المسجّلين على المنصة، وحالة تسجيل هويتهم.", "Everyone registered on the platform, and their identity setup.")}
            />

            {error && <Alert tone="error" className="mb-6">{error}</Alert>}

            {(loading || hasData) && <StatStrip
                className="mb-6 sm:grid-cols-3"
                loading={loading}
                items={[
                    { label: l("الطلاب", "Students"), value: students.length, icon: Users, tone: "pen" },
                    { label: l("سجّلوا وشهم وصوتهم", "Identity set up"), value: ready, icon: ShieldCheck, tone: "pass" },
                    { label: l("لسه ماسجلوش", "Not set up yet"), value: students.length - ready, hint: l("مش هيقدروا يدخلوا امتحان", "Can't take exams yet"), icon: UserX, tone: "warn" },
                ]}
            />}

            {hasData && <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <Segmented
                    label={l("تصفية الطلاب", "Filter students")}
                    value={filter}
                    onChange={setFilter}
                    options={[
                        { value: "all", label: l("الكل", "All") },
                        { value: "missing", label: l("هوية ناقصة", "Missing ID") },
                        { value: "unlocked", label: l("مسموح لهم بإعادة التسجيل", "Re-register allowed") },
                    ]}
                    className="max-w-full self-start overflow-x-auto"
                />
                <Input icon={<Search />} value={query} onChange={(e) => setQuery(e.target.value)} placeholder={l("ابحث بالاسم أو البريد", "Search by name or email")} aria-label={l("بحث", "Search")} className="lg:w-80" />
            </div>}

            <Panel className="overflow-hidden">
                {loading ? (
                    <ListSkeleton rows={5} />
                ) : loadError ? (
                    <LoadFailed detail={loadError} onRetry={load} />
                ) : visible.length === 0 ? (
                    <EmptyState
                        icon={<Users />}
                        title={students.length ? l("مفيش طالب مطابق", "No matching students") : l("لسه مفيش طلاب", "No students yet")}
                        body={students.length ? l("جرّب فلتر أو بحث تاني.", "Try a different filter or search.") : l("الطلاب بيظهروا هنا أول ما يعملوا حساب، ولو فتحوا رابط امتحان.", "Students appear here once they create an account, for example from an exam link.")}
                    />
                ) : (
                    <ul className="divide-y divide-rule">
                        {visible.map((s) => {
                            const scores = statsByName.get(s.full_name.trim()) ?? [];
                            const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
                            const enrolled = s.has_faceprint || s.has_voiceprint;
                            return (
                                <li key={s.id} className="flex flex-wrap items-center gap-x-5 gap-y-3 px-6 py-4 transition-colors hover:bg-sheet-2/40">
                                    <Avatar name={s.full_name} />
                                    <div className="min-w-0 flex-1 basis-48">
                                        <p className="truncate text-base font-extrabold text-ink">{s.full_name}</p>
                                        <p className="truncate text-sm font-bold text-ink-2 ltr">{s.email}</p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Badge tone={s.has_faceprint ? "pass" : "warn"} icon={<ScanFace aria-hidden />}>{s.has_faceprint ? l("الوجه", "Face") : l("بدون وجه", "No face")}</Badge>
                                        <Badge tone={s.has_voiceprint ? "pass" : "warn"} icon={<Mic aria-hidden />}>{s.has_voiceprint ? l("الصوت", "Voice") : l("بدون صوت", "No voice")}</Badge>
                                    </div>
                                    <div className="w-28 text-sm">
                                        <p className="text-base font-extrabold text-ink tabular">{avg != null ? `${formatScore(avg)}%` : "—"}</p>
                                        <p className="font-bold text-ink-2">{scores.length ? countOf(lang, scores.length, NOUNS.exam) : l("لا امتحانات", "No exams")}</p>
                                    </div>
                                    {enrolled ? (
                                        <Button
                                            variant="secondary"
                                            size="sm"
                                            loading={busy === s.id}
                                            onClick={() => toggleReenroll(s)}
                                            className={cn("w-48", s.voice_reenroll_allowed && "border-pass text-pass hover:border-pass hover:bg-pass-wash")}
                                            title={s.voice_reenroll_allowed ? l("اضغط لإلغاء الإذن", "Click to revoke") : l("اسمح للطالب يعيد تسجيل وشه وصوته", "Let the student re-register face and voice")}
                                        >
                                            {s.voice_reenroll_allowed ? <LockOpen className="size-4" aria-hidden /> : <Lock className="size-4" aria-hidden />}
                                            {s.voice_reenroll_allowed ? l("إعادة التسجيل مسموحة", "Re-register allowed") : l("السماح بإعادة التسجيل", "Allow re-register")}
                                        </Button>
                                    ) : (
                                        <span className="w-48 text-center text-sm font-bold text-ink-2">{l("في انتظار التسجيل", "Waiting for setup")}</span>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Panel>
        </>
    );
}
