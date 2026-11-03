import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Inbox, Mic, X } from "lucide-react";
import api from "../lib/api";
import { examTitleOf } from "../lib/types";
import { useI18n } from "../i18n";
import { Panel, PageHeader, RuledList } from "../components/ui/panel";
import { Alert, EmptyState, ListSkeleton, LoadFailed } from "../components/ui/feedback";
import { Badge } from "../components/ui/badge";
import { Button, ButtonLink, buttonClasses } from "../components/ui/button";
import { difficultyInfo, timeAgo } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiErrors";
import type { Assignment } from "../lib/types";

const DISMISSED_KEY = "dismissedExamTokens";

function readDismissed(): string[] {
    try { return JSON.parse(localStorage.getItem(DISMISSED_KEY) || "[]"); } catch { return []; }
}

/** Exam invites for students: assigned exams plus an invite link they opened. */
export default function MessagesPage() {
    const { l, lang } = useI18n();
    const navigate = useNavigate();
    const [items, setItems] = useState<Assignment[]>([]);
    const [dismissed, setDismissed] = useState<string[]>(readDismissed);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        api.get("/exams/my-assignments")
            .then((res) => setItems(res.data))
            .catch((err) => {
                const status = err?.response?.status;
                if (status === 401 || status === 403) {
                    localStorage.removeItem("token");
                    navigate("/login", { replace: true });
                    return;
                }
                setError(getApiErrorMessage(err, l("تعذّر تحميل الدعوات.", "Couldn't load invites.")));
            })
            .finally(() => setLoading(false));
    }, [navigate, l]);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    useEffect(() => { load(); }, [load]);

    let inviteToken: string | null = null;
    try { inviteToken = localStorage.getItem("pendingExamToken"); } catch { /* ignore */ }

    const visible = items.filter((a) => a.status === "pending" && a.exam_token && !dismissed.includes(a.exam_token));
    const showInviteLink = inviteToken && !dismissed.includes(inviteToken) && !items.some((a) => a.exam_token === inviteToken);

    const start = (token: string) => {
        localStorage.setItem("pendingExamToken", token);
        navigate("/exam/start");
    };

    const dismiss = (token: string) => {
        const next = [...dismissed, token];
        setDismissed(next);
        try { localStorage.setItem(DISMISSED_KEY, JSON.stringify(next)); } catch { /* ignore */ }
    };

    const restore = () => {
        setDismissed([]);
        try { localStorage.removeItem(DISMISSED_KEY); } catch { /* ignore */ }
    };

    return (
        <>
            <PageHeader
                title={l("دعوات الامتحانات", "Exam invites")}
                description={l("الامتحانات اللي المحاضرين بعتوهالك. ابدأ أي واحد لما تكون جاهز.", "Exams your lecturers sent you. Start any of them when you're ready.")}
            />

            {showInviteLink && (
                <Alert
                    tone="info"
                    className="mb-6"
                    title={l("امتحان من رابط دعوة", "Exam from an invite link")}
                    action={
                        <div className="flex gap-1">
                            <Button size="sm" onClick={() => start(inviteToken!)}>{l("ابدأ", "Start")}</Button>
                            <button type="button" className={buttonClasses("ghost", "icon-sm")} onClick={() => dismiss(inviteToken!)} aria-label={l("إخفاء", "Hide")}>
                                <X className="size-4" aria-hidden />
                            </button>
                        </div>
                    }
                >
                    {l("فتحت رابط امتحان قبل كده ولسه مابدأتوش.", "You opened an exam link earlier and haven't started it yet.")}
                </Alert>
            )}

            <Panel className="overflow-hidden">
                {loading ? (
                    <ListSkeleton rows={3} />
                ) : error ? (
                    <LoadFailed detail={error} onRetry={load} />
                ) : visible.length === 0 ? (
                    <EmptyState
                        icon={<Inbox />}
                        title={l("مفيش دعوات جديدة", "No new invites")}
                        body={l("لما محاضر يبعتلك امتحان هيظهر هنا وفي الصفحة الرئيسية.", "When a lecturer sends you an exam, it shows up here and on your overview.")}
                        action={dismissed.length > 0
                            ? <Button variant="secondary" onClick={restore}>{l("إظهار الدعوات المخفية", "Show hidden invites")}</Button>
                            : <ButtonLink to="/dashboard/grades" variant="secondary">{l("درجاتي", "My grades")}</ButtonLink>}
                    />
                ) : (
                    <RuledList>
                        {visible.map((a) => {
                            const diff = difficultyInfo(a.question_difficulty, lang);
                            return (
                                <li key={a.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
                                    <div className="min-w-0 flex-1">
                                        <p className="text-sm text-ink-3">
                                            {l(`من ${a.assigned_by_name || "المحاضر"}`, `From ${a.assigned_by_name || "your lecturer"}`)} <span className="ms-2">{timeAgo(a.assigned_at, lang)}</span>
                                        </p>
                                        <p className="mt-0.5 font-semibold leading-snug">{examTitleOf(a, l)}</p>
                                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                                            {a.question_category && a.question_category !== "general" && <Badge>{a.question_category}</Badge>}
                                            {a.question_difficulty && <Badge tone={diff.tone}>{diff.label}</Badge>}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <Button variant="secondary" onClick={() => start(a.exam_token!)} aria-label={`${l("ابدأ الامتحان", "Start exam")}: ${examTitleOf(a, l)}`}><Mic className="size-4" aria-hidden />{l("ابدأ الامتحان", "Start exam")}</Button>
                                        <button type="button" className={buttonClasses("ghost", "icon")} onClick={() => dismiss(a.exam_token!)} aria-label={l("إخفاء الدعوة", "Hide invite")} title={l("إخفاء", "Hide")}>
                                            <X className="size-4" aria-hidden />
                                        </button>
                                    </div>
                                </li>
                            );
                        })}
                    </RuledList>
                )}
            </Panel>
        </>
    );
}
