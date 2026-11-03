import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Check, Plus, Mic, ShieldCheck, ShieldAlert, ScanFace, Inbox, ClipboardList, Lock, EyeOff, Lamp, MessagesSquare, HeartHandshake, PartyPopper } from "lucide-react";
import { cn } from "../lib/utils";
import VoiceEnrollmentModal from "../components/VoiceEnrollmentModal";
import api from "../lib/api";
import { examTitleOf } from "../lib/types";
import { useI18n } from "../i18n";
import { Button, ButtonLink, buttonClasses } from "../components/ui/button";
import { Panel, PanelHeader, RuledList, StatStrip } from "../components/ui/panel";
import { WelcomeBanner, onDark } from "../components/WelcomeBanner";
import { Alert, EmptyState, ListSkeleton, LoadFailed, Skeleton } from "../components/ui/feedback";
import { Avatar } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { ScoreMark } from "../components/ui/score-mark";
import { gradeOf } from "../lib/grades";
import { getApiErrorMessage } from "../lib/apiErrors";
import { countOf, difficultyInfo, NOUNS, parseServerDate, timeAgo } from "../lib/format";
import {
    isLecturerRole, needsReview,
    type Assignment, type BiometricStatus, type Me, type Question, type Submission,
} from "../lib/types";
import { SubscriptionQuotaBar } from "../components/SubscriptionModal";

export default function Overview() {
    const { l, lang } = useI18n();
    const navigate = useNavigate();
    const [user, setUser] = useState<Me | null>(null);
    const [bio, setBio] = useState<BiometricStatus | null>(null);
    const [showEnroll, setShowEnroll] = useState(false);
    const [loading, setLoading] = useState(true);

    // Lecturer data
    const [questions, setQuestions] = useState<Question[]>([]);
    const [results, setResults] = useState<Submission[]>([]);
    // Student data
    const [assignments, setAssignments] = useState<Assignment[]>([]);

    const loadBiometrics = () => {
        api.get("/voice/status").then((r) => setBio(r.data)).catch(() => setBio(null));
    };

    const [loadError, setLoadError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setLoadError("");
        loadBiometrics();
        api.get("/users/me")
            .then(async (res) => {
                setUser(res.data);
                if (isLecturerRole(res.data.role)) {
                    const [q, r] = await Promise.all([api.get("/questions/"), api.get("/exams/all-results")]);
                    setQuestions(q.data);
                    setResults(r.data);
                } else {
                    const a = await api.get("/exams/my-assignments");
                    setAssignments(a.data);
                }
            })
            .catch((err) => {
                const status = err?.response?.status;
                if (status === 401 || status === 403) {
                    localStorage.removeItem("token");
                    navigate("/login", { replace: true });
                    return;
                }
                setLoadError(getApiErrorMessage(err, l("تعذّر تحميل بياناتك.", "Couldn't load your data.")));
            })
            .finally(() => setLoading(false));
    }, [navigate, l]);

    // eslint-disable-next-line react-hooks/set-state-in-effect
    useEffect(() => { load(); }, [load]);

    if (loadError && !loading) {
        return (
            <Panel>
                <LoadFailed onRetry={load} />
            </Panel>
        );
    }

    const firstName = (user?.full_name || "").split(/\s+/).filter((w) => !w.endsWith(".")).slice(0, 1).join(" ");
    const lecturer = isLecturerRole(user?.role);

    if (loading) {
        return (
            <div aria-busy>
                <Skeleton className="mb-3 h-9 w-64" />
                <Skeleton className="mb-8 h-5 w-80" />
                <Skeleton className="mb-8 h-24 w-full rounded-[var(--radius-panel)]" />
                <Panel><ListSkeleton rows={4} /></Panel>
            </div>
        );
    }

    // ── Lecturer ──────────────────────────────────────────────────────────────
    if (lecturer) {
        const exams = new Set(questions.map((q) => q.group_token || q.exam_token)).size;
        const scored = results.filter((r) => r.overall_score != null);
        const avg = scored.length ? Math.round(scored.reduce((s, r) => s + (r.overall_score ?? 0), 0) / scored.length) : null;
        const flagged = results.filter(needsReview);
        const unpublished = results.filter((r) => !r.grade_visible).length;
        const recent = [...results]
            .sort((a, b) => (parseServerDate(b.submitted_at)?.getTime() ?? 0) - (parseServerDate(a.submitted_at)?.getTime() ?? 0))
            .slice(0, 6);

        return (
            <>
                <WelcomeBanner
                    mood={flagged.length > 0 ? "attention" : results.length > 0 && results.every((r) => r.grade_visible) ? "done" : "calm"}
                    title={l(`أهلاً، ${user?.full_name ?? ""}`, `Welcome, ${user?.full_name ?? ""}`)}
                    description={
                        results.length
                            ? `${l("وصلتك", "You have")} ${countOf(lang, results.length, NOUNS.answer)} ${l("حتى الآن", "so far")}${flagged.length ? l(`، منهم ${countOf("ar", flagged.length, NOUNS.answer)} محتاجة مراجعتك.`, `, ${flagged.length} need your review.`) : "."}`
                            : l("ابدأ بإضافة سؤال وابعت رابطه للطلاب، والتصحيح هيوصلك جاهز.", "Add a question and share its link — the grading comes back to you done.")
                    }
                    actions={
                        <>
                            <ButtonLink to="/dashboard/questions?new=1" size="lg" className={onDark.primary}><Plus className="size-5" aria-hidden />{l("سؤال جديد", "New question")}</ButtonLink>
                            {results.length > 0 && <ButtonLink to="/dashboard/results" variant="secondary" size="lg" className={onDark.secondary}>{l("كل النتائج", "All results")}</ButtonLink>}
                        </>
                    }
                    aside={avg != null && (
                        <div className="w-64 rounded-2xl border-2 border-white/20 bg-white/[0.10] p-5">
                            <p className="text-sm font-bold text-white/80">{l("متوسط درجات طلابك", "Your students' average")}</p>
                            <div className="mt-3 flex items-center justify-between">
                                <span className="font-display text-5xl font-extrabold tracking-tight" dir="ltr">{avg}<span className="text-2xl text-white/70">%</span></span>
                                <span className="text-xs font-bold text-white/75">{countOf(lang, scored.length, NOUNS.answer)}</span>
                            </div>
                            <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/20" aria-hidden>
                                <div className="h-full rounded-full bg-white" style={{ width: `${avg}%` }} />
                            </div>
                        </div>
                    )}
                />

                <SubscriptionQuotaBar refreshTrigger={questions.length} />

                {results.length === 0 && (
                    <Panel className="mb-8">
                        <PanelHeader
                            title={l("ابدأ في 3 خطوات", "Get started in 3 steps")}
                            description={l("بعد أول إجابة توصلك، الصفحة دي هتبقى ملخص لكل امتحاناتك.", "Once your first answer arrives, this page becomes a summary of all your exams.")}
                        />
                        <ol className="divide-y divide-rule">
                            {[
                                {
                                    done: questions.length > 0,
                                    title: l("اكتب أول سؤال وإجابته النموذجية", "Write your first question and model answer"),
                                    body: l("الذكاء الاصطناعي بيصحح على أساس الإجابة النموذجية، فاكتبها بالمعنى الكامل.", "The AI grades against the model answer, so write out the full meaning."),
                                    action: <ButtonLink to="/dashboard/questions?new=1" size="md">{l("اكتب سؤال", "Write a question")}</ButtonLink>,
                                },
                                {
                                    done: false,
                                    title: l("ابعت الامتحان للطلاب", "Send the exam to students"),
                                    body: l("انسخ رابط الامتحان وابعته على جروب المادة، أو ابعته لطالب معيّن من صفحة الأسئلة.", "Copy the exam link into your class group, or send it to specific students from the Questions page."),
                                    action: questions.length > 0 ? <ButtonLink to="/dashboard/questions" variant="secondary" size="md">{l("صفحة الأسئلة", "Questions page")}</ButtonLink> : null,
                                },
                                {
                                    done: false,
                                    title: l("راجع الإجابات وانشر الدرجات", "Review answers and publish grades"),
                                    body: l("كل إجابة بتوصلك مصححة، ومعاها نصها وملاحظات النزاهة. الدرجة بتظهر في «درجاتي» عند الطالب بعد ما تنشرها.", "Each answer arrives graded, with its transcript and integrity notes. The grade appears in the student's My grades once you publish it."),
                                    action: null,
                                },
                            ].map((s, i) => (
                                <li key={i} className="flex flex-col gap-3.5 px-6 py-4.5 sm:flex-row sm:items-center">
                                    <span className={cn(
                                        "flex size-9 shrink-0 items-center justify-center rounded-xl border-2 font-display text-base font-extrabold",
                                        s.done ? "border-pass bg-pass text-pen-ink" : "border-pen bg-pen-wash text-ink",
                                    )}>
                                        {s.done ? <Check className="size-4" aria-label={l("تم", "Done")} /> : i + 1}
                                    </span>
                                    <div className="min-w-0 flex-1">
                                        <p className={cn("text-base font-extrabold text-ink", s.done && "text-ink-2 line-through decoration-ink-3")}>{s.title}</p>
                                        <p className="mt-0.5 text-sm font-semibold text-ink-2">{s.body}</p>
                                    </div>
                                    {!s.done && s.action}
                                </li>
                            ))}
                        </ol>
                    </Panel>
                )}

                {results.length > 0 && <StatStrip
                    className="mb-8"
                    items={[
                        { label: l("الامتحانات", "Exams"), value: exams, hint: countOf(lang, questions.length, NOUNS.question), icon: ClipboardList, tone: "pen" },
                        { label: l("الإجابات", "Submissions"), value: results.length, icon: Inbox, tone: "violet" },
                        { label: l("تحتاج مراجعتك", "Need your review"), value: flagged.length, hint: l("النزاهة أو الهوية", "Integrity or identity"), icon: ShieldAlert, tone: "warn" },
                        { label: l("لم تُنشر بعد", "Not published"), value: unpublished, hint: l("الطالب مش شايف درجتها", "Hidden from the student"), icon: EyeOff, tone: "teal" },
                    ]}
                />}

                {flagged.length > 0 && (
                    <Alert
                        tone="warning"
                        className="mb-8"
                        title={l(`${countOf("ar", flagged.length, NOUNS.answer)} فيها ملاحظات نزاهة`, flagged.length === 1 ? "1 answer has integrity notes" : `${flagged.length} answers have integrity notes`)}
                        action={<ButtonLink to="/dashboard/results?filter=review" variant="secondary" size="sm">{l("راجعها", "Review")}</ButtonLink>}
                    >
                        {l("الذكاء الاصطناعي رصد سلوكاً يستحق نظرة منك قبل نشر الدرجة.", "The AI flagged behaviour worth a look before you publish the grade.")}
                    </Alert>
                )}

                {results.length > 0 && <Panel>
                    <PanelHeader
                        title={l("آخر الإجابات", "Latest submissions")}
                        actions={results.length > 0 && <ButtonLink to="/dashboard/results" variant="secondary" size="sm">{l("عرض الكل", "View all")}</ButtonLink>}
                    />
                    {recent.length === 0 ? (
                        <EmptyState
                            icon={<Inbox />}
                            title={l("لا توجد إجابات بعد", "No submissions yet")}
                            body={l("ستظهر هنا إجابات الطلاب فور تسليمها، مصحّحة تلقائياً.", "Student answers appear here as soon as they're submitted, already graded.")}
                            action={<ButtonLink to="/dashboard/questions?new=1"><Plus className="size-4" aria-hidden />{l("أضف أول سؤال", "Add your first question")}</ButtonLink>}
                        />
                    ) : (
                        <RuledList>
                            {recent.map((s) => {
                                const g = gradeOf(s.overall_score);
                                return (
                                    <li key={s.id}>
                                        <Link
                                            to={`/dashboard/results?open=${s.id}`}
                                            className="flex items-center gap-4 px-6 py-4 transition-colors hover:bg-sheet-2"
                                        >
                                            <Avatar name={s.student_name} />
                                            <div className="min-w-0 flex-1">
                                                <p className="truncate text-base font-extrabold text-ink">{s.student_name}</p>
                                                <p className="truncate text-sm font-semibold text-ink-2">
                                                    {s.question_text || l("سؤال محذوف", "Deleted question")}
                                                </p>
                                            </div>
                                            <div className="hidden items-center gap-2 sm:flex">
                                                <span className="text-sm font-bold text-ink-2">{timeAgo(s.submitted_at, lang)}</span>
                                                {needsReview(s) && <Badge tone="warn">{l("مراجعة", "Review")}</Badge>}
                                                {g ? <Badge tone={g.tone}>{l(g.ar, g.en)}</Badge> : <Badge>{l("قيد التصحيح", "Grading")}</Badge>}
                                            </div>
                                            <ScoreMark score={s.overall_score} size="sm" plain className="w-14" />
                                        </Link>
                                    </li>
                                );
                            })}
                        </RuledList>
                    )}
                </Panel>}
            </>
        );
    }

    // ── Student ───────────────────────────────────────────────────────────────
    const pending = assignments.filter((a) => a.status === "pending");
    const ready = !!bio?.biometrics_complete;
    const finishedAll = pending.length === 0 && assignments.length > 0;
    let inviteToken: string | null = null;
    try { inviteToken = localStorage.getItem("pendingExamToken"); } catch { /* ignore */ }
    const inviteOutsideList = inviteToken && !pending.some((a) => a.exam_token === inviteToken);

    const startExam = (token: string | null) => {
        if (!token) return;
        localStorage.setItem("pendingExamToken", token);
        navigate("/exam/start");
    };

    return (
        <>
            <WelcomeBanner
                variant="bright"
                mood={bio && !ready ? "attention" : pending.length > 0 ? "calm" : "done"}
                title={l(`أهلاً، ${firstName}`, `Hi, ${firstName}`)}
                description={
                    pending.length
                        ? l(
                            `عندك ${countOf("ar", pending.length, NOUNS.exam)} في انتظارك. خد نفس، واتكلم براحتك.`,
                            pending.length === 1 ? "You have one exam waiting. Take a breath and speak at your own pace." : `You have ${pending.length} exams waiting. Take a breath and speak at your own pace.`,
                        )
                        : l("مفيش امتحانات مطلوبة منك دلوقتي. هنبلّغك أول ما يوصل جديد.", "No exams are waiting right now. New ones will show up here.")
                }
                actions={pending.length > 0 && ready ? (
                    <button type="button" onClick={() => startExam(pending[0].exam_token)} className={buttonClasses("primary", "lg")}>
                        <Mic className="size-5" aria-hidden />{l("ابدأ أول امتحان", "Start the first exam")}
                    </button>
                ) : pending.length === 0 ? (
                    <ButtonLink to="/dashboard/grades" variant="secondary" size="lg">{l("درجاتي", "My grades")}</ButtonLink>
                ) : undefined}
                aside={
                    pending[0] ? (
                        <div className="w-68 rounded-2xl border border-rule bg-sheet-2/80 p-5">
                            <p className="text-xs font-extrabold text-pen">{l("الامتحان الجاي", "Up next")}</p>
                            <p className="mt-1.5 line-clamp-2 font-display font-bold leading-snug text-ink">{examTitleOf(pending[0], l)}</p>
                            <p className="mt-2 text-xs font-bold text-ink-2">{pending[0].assigned_by_name}</p>
                        </div>
                    ) : finishedAll ? (
                        <div className="flex items-center gap-3 rounded-2xl border border-rule bg-sheet-2/80 px-5 py-3.5">
                            <span className="flex size-10 items-center justify-center rounded-full bg-pass-wash text-pass"><PartyPopper className="size-5" aria-hidden /></span>
                            <p className="text-sm font-bold text-ink">{l("خلّصت كل امتحاناتك", "All exams done")}</p>
                        </div>
                    ) : undefined
                }
            />

            {/* Identity setup */}
            {bio && !ready ? (
                <Alert
                    tone="warning"
                    className="mb-8"
                    title={l("سجّل وجهك وصوتك قبل أول امتحان", "Register your face and voice before your first exam")}
                    action={<Button size="sm" onClick={() => setShowEnroll(true)}>{l("سجّل الآن", "Register now")}</Button>}
                >
                    {l("بنستخدمهم للتأكد إن انت اللي بتجاوب. التسجيل بياخد حوالي دقيقتين.", "We use them to confirm it's you answering. It takes about two minutes.")}
                </Alert>
            ) : bio && ready ? (
                <div className="mb-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm font-bold text-ink-2">
                    <span className="inline-flex items-center gap-1.5"><ScanFace className="size-4 text-pass" aria-hidden />{l("الوجه مسجّل", "Face registered")}</span>
                    <span className="inline-flex items-center gap-1.5"><Mic className="size-4 text-pass" aria-hidden />{l("الصوت مسجّل", "Voice registered")}</span>
                    {bio.can_reenroll ? (
                        <button type="button" onClick={() => setShowEnroll(true)} className="font-extrabold text-pen hover:underline">
                            {l("إعادة التسجيل", "Register again")}
                        </button>
                    ) : (
                        <span className="inline-flex items-center gap-1.5 text-ink-2"><Lock className="size-3.5" aria-hidden />{l("التعديل بإذن المحاضر", "Changes need lecturer approval")}</span>
                    )}
                </div>
            ) : null}

            {inviteOutsideList && ready && (
                <Alert
                    tone="info"
                    className="mb-8"
                    title={l("عندك امتحان من رابط دعوة", "You opened an exam invite link")}
                    action={<Button size="sm" onClick={() => startExam(inviteToken)}>{l("ابدأ الامتحان", "Start exam")}</Button>}
                />
            )}

            <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <div>
            <Panel>
                <PanelHeader title={l("امتحاناتك المطلوبة", "Your exams")} />
                {pending.length === 0 ? (
                    <EmptyState
                        icon={<ClipboardList />}
                        title={finishedAll ? l("خلّصت كل امتحاناتك", "You're all caught up") : l("لسه مفيش امتحانات", "No exams yet")}
                        body={finishedAll
                            ? l("أي امتحان جديد يرسله المحاضر هيظهر هنا، ودرجاتك المنشورة في صفحة الدرجات.", "Any new exam your lecturer sends shows up here; published grades are on the Grades page.")
                            : l("لما المحاضر يبعتلك امتحان هيظهر هنا، وتقدر تبدأه وقت ما تكون جاهز.", "When a lecturer sends you an exam it shows up here, and you can start it when you're ready.")}
                    />
                ) : (
                    <RuledList>
                        {pending.map((a) => {
                            const diff = difficultyInfo(a.question_difficulty, lang);
                            return (
                                <li key={a.id} className="flex flex-col gap-3 px-6 py-4.5 sm:flex-row sm:items-center sm:gap-5">
                                    <div className="min-w-0 flex-1">
                                        <p className="text-base font-extrabold leading-snug text-ink">{examTitleOf(a, l)}</p>
                                        <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm font-bold text-ink-2">
                                            <span>{a.assigned_by_name || l("المحاضر", "Lecturer")}</span>
                                            <span>•</span>
                                            <span>{timeAgo(a.assigned_at, lang)}</span>
                                            {a.question_difficulty && <Badge tone={diff.tone}>{diff.label}</Badge>}
                                        </p>
                                    </div>
                                    <Button
                                        variant={ready ? "secondary" : "primary"}
                                        onClick={() => startExam(a.exam_token)}
                                        aria-label={`${l("ابدأ الامتحان", "Start exam")}: ${examTitleOf(a, l)}`}
                                        disabled={!ready}
                                        title={!ready ? l("سجّل وجهك وصوتك أولاً", "Register your face and voice first") : undefined}
                                        className="sm:w-auto"
                                    >
                                        <Mic className="size-4" aria-hidden />
                                        {l("ابدأ الامتحان", "Start exam")}
                                    </Button>
                                </li>
                            );
                        })}
                    </RuledList>
                )}
            </Panel>

            {ready && (
                <p className="mt-4 flex items-center gap-2 text-sm font-bold text-ink-2">
                    <ShieldCheck className="size-4" aria-hidden />
                    {l("الامتحان بيتسجّل بالصوت، والكاميرا بتتأكد من هويتك أثناء الإجابة.", "Your answer is recorded as audio; the camera confirms your identity while you answer.")}
                </p>
            )}
            </div>

            <CalmTips />
            </div>

            <VoiceEnrollmentModal
                isOpen={showEnroll}
                onClose={() => setShowEnroll(false)}
                onSuccess={() => { setShowEnroll(false); loadBiometrics(); }}
            />
        </>
    );
}

function CalmTips() {
    const { l } = useI18n();
    const tips = [
        { icon: Lamp, tone: "bg-sun-wash text-sun", title: l("مكان هادي ونوره كويس", "A quiet, well-lit spot"), body: l("قعدة مريحة ووشك باين في الكاميرا، وده كل المطلوب.", "Sit comfortably with your face in view — that's all it takes.") },
        { icon: MessagesSquare, tone: "bg-pen-wash text-pen", title: l("اتكلم زي ما بتشرح لصاحبك", "Explain it like you would to a friend"), body: l("التصحيح بيفهم المعنى، مش لازم تحفظ كلام الكتاب بالحرف.", "Grading follows the meaning — no need to recite the book word for word.") },
        { icon: HeartHandshake, tone: "bg-teal-wash text-teal", title: l("لو اتلخبطت، عادي", "Lost your thread? That's fine"), body: l("خد نفس وكمّل من حيث وقفت. الإجابة بتتقيّم كلها مع بعض.", "Take a breath and carry on. Your answer is judged as a whole.") },
    ];
    return (
        <Panel className="p-6">
            <h2 className="font-display text-lg font-extrabold text-ink">{l("عشان امتحانك يعدّي بهدوء", "For a calm exam")}</h2>
            <ul className="mt-4 space-y-4">
                {tips.map(({ icon: Icon, tone, title, body }) => (
                    <li key={title} className="flex gap-3">
                        <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-xl", tone)}><Icon className="size-5" aria-hidden /></span>
                        <div>
                            <p className="font-extrabold leading-snug text-ink">{title}</p>
                            <p className="mt-0.5 text-sm font-semibold leading-relaxed text-ink-2">{body}</p>
                        </div>
                    </li>
                ))}
            </ul>
        </Panel>
    );
}
