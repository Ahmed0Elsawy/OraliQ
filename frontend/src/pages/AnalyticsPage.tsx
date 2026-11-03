import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, CircleCheck, LifeBuoy, ShieldAlert, TrendingUp } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { cn } from "../lib/utils";
import { Panel, PanelHeader, PageHeader, StatStrip } from "../components/ui/panel";
import { EmptyState, LoadFailed, Skeleton } from "../components/ui/feedback";
import { ButtonLink } from "../components/ui/button";
import { ColumnChart } from "../components/charts/ColumnChart";
import { formatScore } from "../lib/grades";
import { countOf, NOUNS, parseServerDate } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiErrors";
import { needsReview, type Submission } from "../lib/types";

const avgOf = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

export default function AnalyticsPage() {
    const { l, lang } = useI18n();
    const [subs, setSubs] = useState<Submission[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        api.get("/exams/all-results")
            .then((res) => setSubs(res.data))
            .catch((err) => setError(getApiErrorMessage(err, l("تعذّر تحميل التحليلات.", "Couldn't load analytics."))))
            .finally(() => setLoading(false));
    }, [l]);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    useEffect(() => { load(); }, [load]);

    const scored = useMemo(() => subs.filter((s) => s.overall_score != null), [subs]);
    const scores = scored.map((s) => s.overall_score as number);
    const avg = avgOf(scores);
    // Backend caps anything under 50 content / 50 overall as a fail (exams.py)
    const passRate = scores.length ? Math.round((scores.filter((s) => s >= 50).length / scores.length) * 100) : null;
    const struggling = scores.filter((s) => s < 50).length;
    const flagged = subs.filter(needsReview).length;

    const bands = (() => {
        const defs = [
            { key: "weak", label: l("ضعيف", "Weak"), range: l("أقل من 45%", "under 45%"), test: (s: number) => s < 45 },
            { key: "fair", label: l("مقبول", "Fair"), range: "45–64%", test: (s: number) => s >= 45 && s < 65 },
            { key: "good", label: l("جيد", "Good"), range: "65–84%", test: (s: number) => s >= 65 && s < 85 },
            { key: "exc", label: l("ممتاز", "Excellent"), range: l("85% فأكثر", "85% and up"), test: (s: number) => s >= 85 },
        ];
        return defs.map((d) => {
            const n = scores.filter(d.test).length;
            return { key: d.key, label: d.label, value: n, detail: [d.range, ...(scores.length ? [l(`${Math.round((n / scores.length) * 100)}% من الطلاب`, `${Math.round((n / scores.length) * 100)}% of students`)] : [])] };
        });
    })();

    const days = (() => {
        const loc = lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB";
        const fmt = new Intl.DateTimeFormat(loc, { day: "numeric" });
        const full = new Intl.DateTimeFormat(loc, { weekday: "long", day: "numeric", month: "long" });
        const out: { key: string; label: string; value: number; detail?: string[] }[] = [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        for (let i = 13; i >= 0; i--) {
            const d = new Date(today);
            d.setDate(today.getDate() - i);
            const next = new Date(d);
            next.setDate(d.getDate() + 1);
            const inDay = subs.filter((s) => {
                const t = parseServerDate(s.submitted_at);
                return t && t >= d && t < next;
            });
            const dayAvg = avgOf(inDay.filter((s) => s.overall_score != null).map((s) => s.overall_score as number));
            out.push({
                key: d.toISOString().slice(0, 10),
                label: fmt.format(d),
                value: inDay.length,
                detail: [full.format(d), ...(dayAvg != null ? [l(`متوسط ${formatScore(dayAvg)}%`, `avg ${formatScore(dayAvg)}%`)] : [])],
            });
        }
        return out;
    })();

    const components = [
        { label: l("المحتوى", "Content"), value: avgOf(scored.map((s) => s.nlp_score).filter((v): v is number => v != null)) },
        { label: l("الطلاقة", "Fluency"), value: avgOf(scored.map((s) => s.speech_score).filter((v): v is number => v != null)) },
        { label: l("النزاهة", "Integrity"), value: avgOf(scored.map((s) => s.facial_score).filter((v): v is number => v != null)) },
    ];

    const byQuestion = useMemo(() => {
        const m = new Map<number, Submission[]>();
        for (const s of scored) m.set(s.question_id, [...(m.get(s.question_id) || []), s]);
        return [...m.entries()]
            .map(([id, list]) => ({
                id,
                text: list[0].question_text || l("سؤال محذوف", "Deleted question"),
                count: list.length,
                avg: avgOf(list.map((s) => s.overall_score as number)) ?? 0,
                content: avgOf(list.map((s) => s.nlp_score).filter((v): v is number => v != null)),
            }))
            .sort((a, b) => a.avg - b.avg);
    }, [scored, l]);

    if (loading) {
        return (
            <>
                <Skeleton className="mb-8 h-9 w-48" />
                <Skeleton className="mb-6 h-24 w-full rounded-[var(--radius-panel)]" />
                <Skeleton className="h-72 w-full rounded-[var(--radius-panel)]" />
            </>
        );
    }

    return (
        <>
            <PageHeader title={l("التحليلات", "Analytics")} description={l("أداء طلابك عبر كل الامتحانات، وأين يحتاجون مساعدة.", "How your students perform across exams, and where they need help.")} />

            {error ? (
                <Panel><LoadFailed detail={error} onRetry={load} /></Panel>
            ) : scored.length === 0 ? (
                <Panel>
                    <EmptyState
                        icon={<BarChart3 />}
                        title={l("مفيش بيانات كفاية لسه", "Not enough data yet")}
                        body={l("التحليلات بتظهر بعد ما الطلاب يسلّموا إجابات مصححة.", "Analytics appear once students submit graded answers.")}
                        action={<ButtonLink to="/dashboard/questions" variant="secondary">{l("أسئلة الامتحانات", "Exam questions")}</ButtonLink>}
                    />
                </Panel>
            ) : (
                <div className="space-y-6">
                    <StatStrip
                        items={[
                            { label: l("متوسط الدرجات", "Average score"), value: avg != null ? `${Math.round(avg)}%` : "—", hint: `${l("من", "from")} ${countOf(lang, scored.length, NOUNS.answer)}`, icon: TrendingUp, tone: "pen" },
                            { label: l("نسبة النجاح", "Pass rate"), value: passRate != null ? `${passRate}%` : "—", hint: l("50% فأكثر", "50% or more"), icon: CircleCheck, tone: "pass" },
                            { label: l("يحتاجون دعم", "Need support"), value: struggling, hint: l("أقل من 50%", "below 50%"), icon: LifeBuoy, tone: "warn" },
                            { label: l("ملاحظات نزاهة", "Integrity notes"), value: flagged, icon: ShieldAlert, tone: "mark" },
                        ]}
                    />

                    <div className="grid gap-6 lg:grid-cols-2 [&>*]:min-w-0">
                        <Panel>
                            <PanelHeader title={l("توزيع الدرجات", "Score distribution")} description={l("عدد الطلاب في كل تقدير", "Students per grade band")} />
                            <div className="p-5">
                                <ColumnChart data={bands} title={l("توزيع الدرجات", "Score distribution")} valueLabel={l("طالب", "students")} labelKeys={bands.map((b) => b.key)} />
                            </div>
                        </Panel>
                        <Panel>
                            <PanelHeader title={l("الإجابات آخر 14 يوم", "Answers, last 14 days")} description={l("عدد الإجابات المسلّمة يومياً", "Answers submitted per day")} />
                            <div className="p-5">
                                <ColumnChart data={days} title={l("الإجابات آخر 14 يوم", "Answers, last 14 days")} valueLabel={l("إجابة", "answers")} />
                            </div>
                        </Panel>
                    </div>

                    <Panel>
                        <PanelHeader title={l("متوسط كل عنصر", "Average by component")} description={l("أي جزء من الدرجة بيشد المتوسط لتحت", "Which part of the grade pulls the average down")} />
                        <dl className="grid gap-5 p-5 sm:grid-cols-3">
                            {components.map((c) => (
                                <div key={c.label} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-y-2">
                                    <dt className="font-semibold">{c.label}</dt>
                                    <dd className="font-display text-lg font-semibold">{c.value != null ? `${Math.round(c.value)}%` : "—"}</dd>
                                    <dd className="col-span-2 h-1.5 overflow-hidden rounded-full bg-pen-wash" aria-hidden>
                                        <div className={cn("h-full rounded-full", c.value != null && c.value < 50 ? "bg-mark" : "bg-chart")} style={{ width: `${Math.min(100, c.value ?? 0)}%` }} />
                                    </dd>
                                </div>
                            ))}
                        </dl>
                    </Panel>

                    <Panel className="overflow-hidden">
                        <PanelHeader title={l("الأسئلة الأصعب على الطلاب", "Hardest questions")} description={l("مرتبة من الأقل متوسطاً. سؤال متوسطه واطي غالباً محتاج يتشرح تاني أو تتراجع إجابته النموذجية.", "Lowest average first. A low average often means the topic needs re-teaching, or the model answer needs a look.")} />
                        <table className="w-full text-sm">
                            <thead className="bg-sheet-2 text-ink-2">
                                <tr>
                                    <th scope="col" className="px-5 py-2.5 text-start font-medium">{l("السؤال", "Question")}</th>
                                    <th scope="col" className="hidden px-3 py-2.5 text-end font-medium sm:table-cell">{l("إجابات", "Answers")}</th>
                                    <th scope="col" className="hidden px-3 py-2.5 text-end font-medium md:table-cell">{l("المحتوى", "Content")}</th>
                                    <th scope="col" className="w-48 px-5 py-2.5 text-start font-medium">{l("المتوسط", "Average")}</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-rule">
                                {byQuestion.map((q) => (
                                    <tr key={q.id}>
                                        <td className="px-5 py-3 leading-snug">{q.text}</td>
                                        <td className="hidden px-3 py-3 text-end tabular text-ink-2 sm:table-cell">{q.count}</td>
                                        <td className="hidden px-3 py-3 text-end tabular text-ink-2 md:table-cell">{q.content != null ? `${Math.round(q.content)}%` : "—"}</td>
                                        <td className="px-5 py-3">
                                            <div className="flex items-center gap-3">
                                                <span className="w-11 shrink-0 font-semibold tabular">{Math.round(q.avg)}%</span>
                                                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-pen-wash" aria-hidden>
                                                    <div className={cn("h-full rounded-full", q.avg < 50 ? "bg-mark" : "bg-chart")} style={{ width: `${Math.min(100, q.avg)}%` }} />
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </Panel>
                </div>
            )}
        </>
    );
}
