import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Check, ChevronDown, ClipboardList, Clock, Copy, Eye, EyeOff, Megaphone, Plus, Search, Trash2, UserPlus } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { cn } from "../lib/utils";
import VoiceRecordButton from "../components/VoiceRecordButton";
import { Button } from "../components/ui/button";
import { Field, Input, Textarea } from "../components/ui/input";
import { Panel, PageHeader } from "../components/ui/panel";
import { Alert, EmptyState, ListSkeleton, LoadFailed, Modal, Segmented } from "../components/ui/feedback";
import { Badge } from "../components/ui/badge";
import { Avatar } from "../components/ui/avatar";
import { countOf, difficultyInfo, formatDate, NOUNS, parseServerDate } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiErrors";
import type { Question, StudentRow } from "../lib/types";
import { useToast } from "../components/ui/toast";
import { useFieldErrors } from "../lib/useFieldErrors";
import { SubscriptionQuotaBar } from "../components/SubscriptionModal";

type Difficulty = "easy" | "medium" | "hard";

interface ExamGroup {
    token: string;
    questions: Question[];
    createdAt: string | null;
}

type ResultsPolicy = "manual" | "immediate";

const emptyDraft = { text: "", model_answer: "", keywords: "", category: "", difficulty: "medium" as Difficulty, duration_minutes: 2, max_attempts: 1, results_policy: "manual" as ResultsPolicy };

export default function Dashboard() {
    const { l, lang } = useI18n();
    const toast = useToast();
    const [params, setParams] = useSearchParams();
    const [questions, setQuestions] = useState<Question[]>([]);
    const [loading, setLoading] = useState(true);
    const [pageError, setPageError] = useState("");
    const [loadError, setLoadError] = useState("");
    const { errors: fieldErrors, validate, clear: clearField, reset: resetFields } = useFieldErrors();
    const editorFields = useRef<HTMLDivElement>(null);
    const [copied, setCopied] = useState<string | null>(null);

    // Editor
    const [editorOpen, setEditorOpen] = useState(false);
    const [draft, setDraft] = useState(emptyDraft);
    const [groupToken, setGroupToken] = useState<string | null>(null);
    const [addedNow, setAddedNow] = useState<Question[]>([]);
    const [saving, setSaving] = useState(false);
    const [editorError, setEditorError] = useState("");

    // Publish results (exams whose grades wait for the lecturer)
    const [toPublish, setToPublish] = useState<ExamGroup | null>(null);
    const [publishing, setPublishing] = useState(false);

    // Delete
    const [toDelete, setToDelete] = useState<Question | null>(null);
    const [deleting, setDeleting] = useState(false);

    // Assign
    const [assignFor, setAssignFor] = useState<ExamGroup | null>(null);
    const [students, setStudents] = useState<StudentRow[] | null>(null);
    const [studentQuery, setStudentQuery] = useState("");
    const [assigned, setAssigned] = useState<Set<number>>(new Set());
    const [busyStudent, setBusyStudent] = useState<number | null>(null);
    const [assignError, setAssignError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setLoadError("");
        api.get("/questions/")
            .then((res) => setQuestions(res.data))
            .catch((err) => setLoadError(getApiErrorMessage(err, l("تعذّر تحميل الأسئلة.", "Couldn't load questions."))))
            .finally(() => setLoading(false));
    }, [l]);
    useEffect(() => { load(); }, [load]);

    // /dashboard/questions?new=1 opens the editor straight away
    useEffect(() => {
        if (params.get("new")) {
            openEditor(null);
            const next = new URLSearchParams(params);
            next.delete("new");
            setParams(next, { replace: true });
        }
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const groups = useMemo<ExamGroup[]>(() => {
        const map = new Map<string, Question[]>();
        for (const q of questions) {
            const key = q.group_token || q.exam_token;
            map.set(key, [...(map.get(key) || []), q]);
        }
        return [...map.entries()]
            .map(([token, qs]) => {
                const sorted = [...qs].sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0));
                return { token, questions: sorted, createdAt: sorted[0]?.created_at ?? null };
            })
            .sort((a, b) => (parseServerDate(b.createdAt)?.getTime() ?? 0) - (parseServerDate(a.createdAt)?.getTime() ?? 0));
    }, [questions]);

    const categories = useMemo(() => [...new Set(questions.map((q) => q.category).filter((c) => c && c !== "general"))], [questions]);

    const examLink = (token: string) => `${window.location.origin}/exam/${token}`;
    const copyLink = async (token: string) => {
        try {
            await navigator.clipboard.writeText(examLink(token));
            setCopied(token);
            toast(l("اتنسخ رابط الامتحان. ابعته للطلاب.", "Exam link copied. Send it to your students."));
            setTimeout(() => setCopied((c) => (c === token ? null : c)), 2000);
        } catch {
            setPageError(l("المتصفح منع النسخ. انسخ الرابط يدوياً من الخانة.", "The browser blocked copying. Copy the link from the field."));
        }
    };

    // ── Editor ────────────────────────────────────────────────────────────────
    const openEditor = (group: ExamGroup | null) => {
        setGroupToken(group?.token ?? null);
        setDraft({ ...emptyDraft, category: group?.questions[0]?.category && group.questions[0].category !== "general" ? group.questions[0].category : "" });
        setAddedNow([]);
        setEditorError("");
        resetFields();
        setEditorOpen(true);
    };

    const save = async (addAnother: boolean) => {
        if (!validate(editorFields.current)) return;
        setSaving(true);
        setEditorError("");
        try {
            const payload = {
                ...draft,
                text: draft.text.trim(),
                model_answer: draft.model_answer.trim(),
                category: draft.category.trim() || "general",
                ...(groupToken ? { group_token: groupToken } : {}),
            };
            const { data } = await api.post("/questions/", payload);
            setQuestions((p) => [...p, data]);
            setAddedNow((p) => [...p, data]);
            if (!groupToken) setGroupToken(data.group_token);
            setDraft((d) => ({ ...emptyDraft, category: d.category, difficulty: d.difficulty, duration_minutes: d.duration_minutes, max_attempts: d.max_attempts, results_policy: d.results_policy }));
            if (!addAnother) {
                setEditorOpen(false);
                toast(l("اتحفظ السؤال", "Question saved"));
            }
        } catch (err) {
            setEditorError(getApiErrorMessage(err, l("تعذّر حفظ السؤال.", "Couldn't save the question.")));
        } finally {
            setSaving(false);
        }
    };

    // ── Publish results ───────────────────────────────────────────────────────
    // The server decides: only this exam's lecturer can publish, and publishing twice changes nothing.
    const confirmPublish = async () => {
        if (!toPublish) return;
        setPublishing(true);
        try {
            const { data } = await api.post(`/exams/publish-results/${toPublish.token}`);
            const ids = new Set(toPublish.questions.map((q) => q.id));
            setQuestions((p) => p.map((q) => (ids.has(q.id) ? { ...q, results_published_at: data.published_at } : q)));
            setToPublish(null);
            toast(l("اتنشرت النتائج — كل طالب يقدر يشوف درجاته دلوقتي.", "Results published — each student can now see their grades."));
        } catch (err) {
            toast(getApiErrorMessage(err, l("تعذّر نشر النتائج.", "Couldn't publish the results.")), "error");
        } finally {
            setPublishing(false);
        }
    };

    // ── Delete ────────────────────────────────────────────────────────────────
    const confirmDelete = async () => {
        if (!toDelete) return;
        setDeleting(true);
        try {
            await api.delete(`/questions/${toDelete.id}`);
            setQuestions((p) => p.filter((q) => q.id !== toDelete.id));
            setToDelete(null);
            toast(l("اتحذف السؤال", "Question deleted"));
        } catch (err) {
            setPageError(getApiErrorMessage(err, l("تعذّر حذف السؤال. لو عليه إجابات طلاب، مش هينفع يتحذف.", "Couldn't delete. Questions with student answers can't be deleted.")));
            setToDelete(null);
        } finally {
            setDeleting(false);
        }
    };

    // ── Assign ────────────────────────────────────────────────────────────────
    const openAssign = async (g: ExamGroup) => {
        setAssignFor(g);
        setAssigned(new Set());
        setStudentQuery("");
        setAssignError("");
        if (!students) {
            try { setStudents((await api.get("/exams/students")).data); }
            catch (err) { setStudents([]); setAssignError(getApiErrorMessage(err, l("تعذّر تحميل الطلاب.", "Couldn't load students."))); }
        }
    };

    const assign = async (sid: number) => {
        const leader = assignFor?.questions[0];
        if (!leader) return;
        setBusyStudent(sid);
        setAssignError("");
        try {
            await api.post("/exams/assign", { question_id: leader.id, student_id: sid });
            setAssigned((s) => new Set(s).add(sid));
            const name = students?.find((x) => x.id === sid)?.full_name;
            toast(l(`اتبعت الامتحان لـ ${name ?? "الطالب"}`, `Exam sent to ${name ?? "the student"}`));
        } catch (err) {
            setAssignError(getApiErrorMessage(err, l("تعذّر إرسال الامتحان.", "Couldn't send the exam.")));
        } finally {
            setBusyStudent(null);
        }
    };

    const filteredStudents = (students ?? []).filter((s) => {
        const q = studentQuery.trim().toLowerCase();
        return !q || s.full_name.toLowerCase().includes(q) || s.email.toLowerCase().includes(q);
    });

    const difficulties: { value: Difficulty; label: string }[] = [
        { value: "easy", label: l("سهل", "Easy") },
        { value: "medium", label: l("متوسط", "Medium") },
        { value: "hard", label: l("صعب", "Hard") },
    ];

    return (
        <>
            <PageHeader
                title={l("أسئلة الامتحانات", "Exam questions")}
                description={l("كل امتحان له رابط واحد. الطالب بيجاوب على أسئلته بالترتيب.", "Each exam has one link. Students answer its questions in order.")}
                actions={
                    <Button size="lg" onClick={() => openEditor(null)}>
                        <Plus className="size-5" aria-hidden />
                        {l("امتحان جديد", "New exam")}
                    </Button>
                }
            />

            <SubscriptionQuotaBar refreshTrigger={questions.length} />

            {pageError && (
                <Alert
                    tone="error"
                    className="mb-6"
                    action={<button className="text-sm font-extrabold text-pen" onClick={() => setPageError("")}>{l("إغلاق", "Dismiss")}</button>}
                >
                    {pageError}
                </Alert>
            )}

            {loading ? (
                <Panel><ListSkeleton rows={4} /></Panel>
            ) : loadError ? (
                <Panel><LoadFailed detail={loadError} onRetry={load} /></Panel>
            ) : groups.length === 0 ? (
                <Panel>
                    <EmptyState
                        icon={<ClipboardList />}
                        title={l("لسه مفيش امتحانات", "No exams yet")}
                        body={l("اكتب السؤال وإجابته النموذجية، والذكاء الاصطناعي هيصحح إجابات الطلاب على أساسها.", "Write a question and its model answer — the AI grades student answers against it.")}
                        action={
                            <Button size="lg" onClick={() => openEditor(null)}>
                                <Plus className="size-5" aria-hidden />
                                {l("أنشئ أول امتحان", "Create your first exam")}
                            </Button>
                        }
                    />
                </Panel>
            ) : (
                <div className="space-y-6">
                    {groups.map((g) => {
                        const total = g.questions.reduce((s, q) => s + (q.duration_minutes || 0), 0);
                        const category = g.questions[0]?.category;
                        return (
                            <Panel key={g.token} className="overflow-hidden">
                                <header className="flex flex-col gap-4 border-b-2 border-rule bg-sheet-2/70 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
                                    <div className="min-w-0">
                                        <h2 className="text-xl font-extrabold text-ink sm:text-2xl">
                                            {category && category !== "general" ? category : l("امتحان شفوي", "Oral exam")}
                                        </h2>
                                        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm font-bold text-ink-2">
                                            <Badge tone="pen">{countOf(lang, g.questions.length, NOUNS.question)}</Badge>
                                            <Badge tone="neutral" icon={<Clock aria-hidden />}>{countOf(lang, total, NOUNS.minute)}</Badge>
                                            <span className="px-1 font-bold text-ink-2">{formatDate(g.createdAt, lang)}</span>
                                            {g.questions[0]?.results_policy === "immediate" ? (
                                                <Badge tone="neutral" icon={<Eye aria-hidden />}>{l("الدرجات بتظهر بعد التصحيح", "Grades shown once graded")}</Badge>
                                            ) : g.questions[0]?.results_published_at ? (
                                                <Badge tone="pass" icon={<Check aria-hidden />}>{l("النتائج منشورة", "Results published")}</Badge>
                                            ) : (
                                                <Badge tone="warn" icon={<EyeOff aria-hidden />}>{l("النتائج لسه مخفية عن الطلاب", "Results hidden from students")}</Badge>
                                            )}
                                        </div>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2.5">
                                        {g.questions[0]?.results_policy !== "immediate" && !g.questions[0]?.results_published_at && (
                                            <Button variant="secondary" size="md" onClick={() => setToPublish(g)}>
                                                <Megaphone className="size-4" aria-hidden />
                                                {l("نشر النتائج", "Publish results")}
                                            </Button>
                                        )}
                                        <Button variant="secondary" size="md" onClick={() => copyLink(g.token)} aria-live="polite">
                                            {copied === g.token ? <Check className="size-4 text-pass" aria-hidden /> : <Copy className="size-4" aria-hidden />}
                                            {copied === g.token ? l("اتنسخ الرابط", "Copied") : l("نسخ الرابط", "Copy link")}
                                        </Button>
                                        <Button variant="secondary" size="md" onClick={() => openAssign(g)}>
                                            <UserPlus className="size-4" aria-hidden />
                                            {l("إرسال لطالب", "Send to student")}
                                        </Button>
                                        <Button variant="primary" size="md" onClick={() => openEditor(g)}>
                                            <Plus className="size-4" aria-hidden />
                                            {l("إضافة سؤال", "Add question")}
                                        </Button>
                                    </div>
                                </header>

                                <ol className="divide-y divide-rule">
                                    {g.questions.map((q, i) => {
                                        const diff = difficultyInfo(q.difficulty, lang);
                                        return (
                                            <li key={q.id} className="group/q">
                                                <details className="[&[open]_.chev]:rotate-180">
                                                    <summary className="flex cursor-pointer list-none items-start gap-4 px-6 py-5 transition-colors hover:bg-sheet-2/60 [&::-webkit-details-marker]:hidden">
                                                        <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl border-2 border-rule-strong bg-pen-wash font-display text-base font-extrabold tabular text-ink">
                                                            {i + 1}
                                                        </span>
                                                        <div className="min-w-0 flex-1">
                                                            <p className="text-base font-extrabold leading-relaxed text-ink sm:text-lg">{q.text}</p>
                                                            <p className="mt-2 flex flex-wrap items-center gap-2 text-sm font-bold text-ink-2">
                                                                <Badge tone={diff.tone}>{diff.label}</Badge>
                                                                <span className="inline-flex items-center gap-1 rounded-full border border-rule-strong bg-sheet-2 px-3 py-0.5 text-xs font-extrabold text-ink">
                                                                    <Clock className="size-3.5" aria-hidden />
                                                                    {countOf(lang, q.duration_minutes, NOUNS.minute)}
                                                                </span>
                                                            </p>
                                                        </div>
                                                        <span className="mt-1 inline-flex items-center gap-1.5 rounded-lg border border-rule-strong bg-sheet-2 px-3 py-1.5 text-xs font-extrabold text-ink transition-colors group-hover/q:border-ink">
                                                            <span className="hidden sm:inline">{l("الإجابة النموذجية", "Model answer")}</span>
                                                            <ChevronDown className="chev size-4 shrink-0 text-ink transition-transform" aria-hidden />
                                                        </span>
                                                    </summary>
                                                    <div className="space-y-4 border-t border-rule bg-sheet-2 px-6 py-5 ps-18">
                                                        <div>
                                                            <p className="text-sm font-extrabold text-ink-2">{l("الإجابة النموذجية", "Model answer")}</p>
                                                            <p className="mt-1.5 rounded-xl border border-rule-strong bg-sheet p-4 text-base font-semibold leading-relaxed text-ink">
                                                                {q.model_answer}
                                                            </p>
                                                        </div>
                                                        {q.keywords && (
                                                            <div>
                                                                <p className="text-sm font-extrabold text-ink-2">{l("كلمات مفتاحية", "Keywords")}</p>
                                                                <div className="mt-1.5 flex flex-wrap gap-1.5">
                                                                    {q.keywords.split(/[,،]/).map((k) => k.trim()).filter(Boolean).map((k) => <Badge key={k}>{k}</Badge>)}
                                                                </div>
                                                            </div>
                                                        )}
                                                        <div>
                                                            <Button variant="danger-ghost" size="sm" onClick={() => setToDelete(q)}>
                                                                <Trash2 className="size-4" aria-hidden />
                                                                {l("حذف السؤال", "Delete question")}
                                                            </Button>
                                                        </div>
                                                    </div>
                                                </details>
                                            </li>
                                        );
                                    })}
                                </ol>
                            </Panel>
                        );
                    })}
                </div>
            )}

            {/* ── Editor ── */}
            <Modal
                open={editorOpen}
                onClose={() => !saving && setEditorOpen(false)}
                size="lg"
                title={groupToken ? l("إضافة سؤال للامتحان", "Add a question") : l("امتحان جديد", "New exam")}
                description={l("الإجابة النموذجية هي اللي هيتقارن بيها كلام الطالب، فاكتبها بالمعنى الكامل.", "Student answers are compared against the model answer, so write out the full meaning.")}
                footer={
                    <>
                        <Button variant="ghost" onClick={() => setEditorOpen(false)} disabled={saving} className="me-auto">
                            {addedNow.length ? l("تم", "Done") : l("إلغاء", "Cancel")}
                        </Button>
                        <Button variant="secondary" onClick={() => save(true)} disabled={saving}>{l("حفظ وإضافة سؤال آخر", "Save and add another")}</Button>
                        <Button onClick={() => save(false)} loading={saving}>{l("حفظ", "Save")}</Button>
                    </>
                }
            >
                {addedNow.length > 0 && (
                    <Alert tone="success" className="mb-5" title={l(`اتضاف ${countOf("ar", addedNow.length, NOUNS.question)} للامتحان`, `${countOf("en", addedNow.length, NOUNS.question)} added to this exam`)}>
                        <ol className="mt-1 list-decimal space-y-0.5 ps-5">
                            {addedNow.map((q) => <li key={q.id} className="truncate">{q.text}</li>)}
                        </ol>
                    </Alert>
                )}
                {editorError && <Alert tone="error" className="mb-5">{editorError}</Alert>}

                <div ref={editorFields} className="grid gap-5">
                    <Field
                        label={l("السؤال", "Question")} htmlFor="q-text" error={fieldErrors["q-text"] && l("اكتب السؤال اللي الطالب هيجاوب عليه.", "Write the question the student will answer.")}
                        action={<VoiceRecordButton hint={l("سؤال امتحان شفوي", "oral exam question")} onTranscribed={(t) => setDraft((d) => ({ ...d, text: d.text ? `${d.text} ${t}` : t }))} />}
                    >
                        <Textarea id="q-text" data-autofocus required rows={3} value={draft.text} onChange={(e) => { setDraft({ ...draft, text: e.target.value }); clearField("q-text"); }} placeholder={l("مثال: عرّف الذكاء الاصطناعي واذكر مثالين على استخدامه", "e.g. Define artificial intelligence and give two examples")} />
                    </Field>
                    <Field
                        label={l("الإجابة النموذجية", "Model answer")} htmlFor="q-answer" error={fieldErrors["q-answer"] && l("اكتب الإجابة النموذجية؛ التصحيح بيقارن بيها.", "Write the model answer; grading compares against it.")}
                        action={<VoiceRecordButton hint={draft.text} onTranscribed={(t) => setDraft((d) => ({ ...d, model_answer: d.model_answer ? `${d.model_answer} ${t}` : t }))} />}
                    >
                        <Textarea id="q-answer" required rows={4} value={draft.model_answer} onChange={(e) => { setDraft({ ...draft, model_answer: e.target.value }); clearField("q-answer"); }} />
                    </Field>
                    <Field label={l("كلمات مفتاحية", "Keywords")} htmlFor="q-keywords" hint={l("اختياري. مصطلحات لازم تيجي في الإجابة، افصل بينها بفاصلة.", "Optional. Terms the answer must mention, separated by commas.")}>
                        <Input id="q-keywords" value={draft.keywords} onChange={(e) => setDraft({ ...draft, keywords: e.target.value })} placeholder={l("محاكاة، تعلم، بيانات", "simulation, learning, data")} aria-describedby="q-keywords-hint" />
                    </Field>
                    <div className="grid gap-5 sm:grid-cols-[1fr_auto_8rem]">
                        <Field label={l("المادة أو الموضوع", "Subject")} htmlFor="q-category">
                            <Input id="q-category" list="q-categories" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} placeholder={l("مثال: تعلم الآلة", "e.g. Machine learning")} />
                            <datalist id="q-categories">{categories.map((c) => <option key={c} value={c} />)}</datalist>
                        </Field>
                        <div className="flex flex-col gap-2">
                            <span className="text-[0.95rem] font-extrabold text-ink" id="q-diff-label">{l("الصعوبة", "Difficulty")}</span>
                            <Segmented label={l("الصعوبة", "Difficulty")} value={draft.difficulty} onChange={(v) => setDraft({ ...draft, difficulty: v })} options={difficulties} />
                        </div>
                        <Field label={l("الوقت (دقائق)", "Time (min)")} htmlFor="q-duration">
                            <Input id="q-duration" type="number" min={1} max={10} value={draft.duration_minutes} className="tabular"
                                onChange={(e) => setDraft({ ...draft, duration_minutes: Math.min(10, Math.max(1, parseInt(e.target.value) || 1)) })} />
                        </Field>
                    </div>
                    {/* When students see grades: also the whole exam's, chosen with its first question. */}
                    {!groupToken && (
                        <fieldset>
                            <legend className="mb-2 text-[0.95rem] font-extrabold text-ink">{l("ظهور الدرجات للطلاب", "When students see grades")}</legend>
                            <div className="grid gap-2 sm:grid-cols-2" role="radiogroup">
                                {([
                                    ["immediate", l("إظهار الدرجات فور انتهاء التصحيح", "Show grades as soon as grading finishes")],
                                    ["manual", l("إخفاء الدرجات حتى أقوم بنشر النتائج", "Hide grades until I publish the results")],
                                ] as [ResultsPolicy, string][]).map(([value, label]) => (
                                    <label key={value} className={cn(
                                        "flex cursor-pointer items-center gap-2.5 rounded-xl border px-3.5 py-3 text-sm font-bold transition-colors",
                                        draft.results_policy === value ? "border-pen bg-pen-wash text-ink" : "border-rule bg-sheet text-ink-2 hover:border-ink-3",
                                    )}>
                                        <input type="radio" name="results-policy" value={value} checked={draft.results_policy === value}
                                            onChange={() => setDraft({ ...draft, results_policy: value })} className="accent-[currentColor]" />
                                        {label}
                                    </label>
                                ))}
                            </div>
                        </fieldset>
                    )}
                    {/* Attempts belong to the whole exam: set with its first question, inherited by the rest. */}
                    {!groupToken && (
                        <Field label={l("عدد المحاولات لكل طالب", "Attempts per student")} htmlFor="q-attempts"
                            hint={l("كل محاولة جلسة امتحان كاملة بوقتها. الافتراضي محاولة واحدة.", "Each attempt is a full timed sitting. Default: one.")}>
                            <Input id="q-attempts" type="number" min={1} max={10} value={draft.max_attempts} className="tabular max-w-[8rem]"
                                aria-describedby="q-attempts-hint"
                                onChange={(e) => setDraft({ ...draft, max_attempts: Math.min(10, Math.max(1, parseInt(e.target.value) || 1)) })} />
                        </Field>
                    )}
                </div>
            </Modal>

            {/* ── Publish results confirm ── */}
            <Modal
                open={!!toPublish}
                onClose={() => !publishing && setToPublish(null)}
                size="sm"
                title={l("نشر نتائج الامتحان؟", "Publish this exam's results?")}
                description={l(
                    "كل طالب هيقدر يشوف درجته وتفاصيل تصحيحه هو بس. الإجابات اللي لسه بتتصحح هتظهر أول ما تخلص. النشر مش بيترجع فيه من هنا.",
                    "Each student will see only their own grade and its details. Answers still being graded appear as soon as they finish. Publishing can't be undone from here.",
                )}
                footer={
                    <>
                        <Button variant="secondary" onClick={() => setToPublish(null)} disabled={publishing}>{l("إلغاء", "Cancel")}</Button>
                        <Button onClick={confirmPublish} loading={publishing}>{l("نشر النتائج", "Publish results")}</Button>
                    </>
                }
            />

            {/* ── Delete confirm ── */}
            <Modal
                open={!!toDelete}
                onClose={() => !deleting && setToDelete(null)}
                size="sm"
                title={l("حذف السؤال؟", "Delete this question?")}
                description={toDelete?.text}
                footer={
                    <>
                        <Button variant="secondary" onClick={() => setToDelete(null)} disabled={deleting}>{l("إلغاء", "Cancel")}</Button>
                        <Button variant="danger" onClick={confirmDelete} loading={deleting}>{l("حذف", "Delete")}</Button>
                    </>
                }
            />

            {/* ── Assign ── */}
            <Modal
                open={!!assignFor}
                onClose={() => setAssignFor(null)}
                title={l("إرسال الامتحان لطالب", "Send exam to a student")}
                description={l("الامتحان هيظهر عند الطالب في صفحة دعوات الامتحانات.", "The exam appears on the student's Exam invites page.")}
                footer={<Button onClick={() => setAssignFor(null)}>{l("تم", "Done")}</Button>}
            >
                {assignError && <Alert tone="error" className="mb-4">{assignError}</Alert>}
                <Input data-autofocus icon={<Search />} value={studentQuery} onChange={(e) => setStudentQuery(e.target.value)} placeholder={l("ابحث بالاسم أو البريد", "Search by name or email")} aria-label={l("بحث عن طالب", "Search students")} />
                <div className="mt-4 max-h-[50vh] overflow-y-auto rounded-[var(--radius-control)] border-2 border-rule-strong">
                    {students === null ? (
                        <ListSkeleton rows={3} />
                    ) : filteredStudents.length === 0 ? (
                        <p className="px-4 py-10 text-center font-bold text-ink-2">{students.length ? l("مفيش طالب بالاسم ده.", "No student matches that search.") : l("لسه مفيش طلاب مسجلين.", "No students have signed up yet.")}</p>
                    ) : (
                        <ul className="divide-y divide-rule">
                            {filteredStudents.map((s) => {
                                const done = assigned.has(s.id);
                                const bioReady = s.has_voiceprint && s.has_faceprint;
                                return (
                                    <li key={s.id} className="flex flex-wrap items-center gap-3 px-4 py-3.5">
                                        <Avatar name={s.full_name} size="sm" />
                                        <div className="min-w-0 flex-1">
                                            <p className="truncate font-extrabold text-ink">{s.full_name}</p>
                                            <p className="truncate text-xs font-bold text-ink-2 ltr">{s.email}</p>
                                        </div>
                                        {!bioReady && <Badge tone="warn">{l("لم يسجل هويته", "No ID setup")}</Badge>}
                                        <Button size="sm" variant="secondary" disabled={done} loading={busyStudent === s.id} onClick={() => assign(s.id)} className={cn(done && "border-pass text-pass")}>
                                            {done ? <><Check className="size-4" aria-hidden />{l("اتبعت", "Sent")}</> : l("إرسال", "Send")}
                                        </Button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            </Modal>
        </>
    );
}
