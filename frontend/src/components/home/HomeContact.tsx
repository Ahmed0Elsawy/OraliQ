import { useRef, useState } from "react";
import { Mail, MapPin, Phone, Send } from "lucide-react";
import { useI18n } from "../../i18n";
import { cn } from "../../lib/utils";
import { COMPANY, telHref } from "../../content/company";
import { useFieldErrors } from "../../lib/useFieldErrors";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { BTN, Eyebrow, H2, Section } from "./ui";

const FIELD =
    "auth-light-input block w-full rounded-xl border border-rule bg-sheet px-4 py-3.5 text-base font-medium text-ink placeholder:text-field focus:border-pen focus:outline-none focus:ring-2 focus:ring-pen/25";

/**
 * Section 6 (#contact): Contact Us
 * Rounded-top Mocha/Espresso stage with Warm Off-White contact cards and theme-aware form card.
 */
export function HomeContact() {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);
    const [sent, setSent] = useState(false);
    const { errors, validate, clear } = useFieldErrors();

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-contact-card]",
                { y: 28, opacity: 0, scale: 0.96 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: 0.65,
                    stagger: 0.1,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-contact-wrap]", start: "top 82%" },
                },
            );
        });
    }, { scope: root, dependencies: [lang] });

    const submit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        if (!validate(e.currentTarget)) return;
        const f = new FormData(e.currentTarget);
        const name = String(f.get("name") || "").trim();
        const from = String(f.get("email") || "").trim();
        const message = String(f.get("message") || "").trim();
        const subject = l(`رسالة من ${name} عن OralIQ`, `A message from ${name} about OralIQ`);
        const body = `${message}\n\n— ${name}${from ? ` <${from}>` : ""}`;
        window.location.href = `mailto:${COMPANY.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
        setSent(true);
    };

    const field = (id: string, label: string, input: React.ReactNode) => (
        <div>
            <label htmlFor={id} className="mb-2 block text-sm font-bold text-ink">
                {label}
            </label>
            {input}
            {errors[id] && (
                <p id={`${id}-error`} className="mt-1.5 text-sm font-bold text-mark">
                    {errors[id]}
                </p>
            )}
        </div>
    );

    return (
        <Section
            id="contact"
            tone="b"
            className="wb-mocha-stage rounded-t-[24px] sm:rounded-t-[32px] mx-2 sm:mx-4 py-16 sm:py-24 lg:py-32"
        >
            <div
                ref={root}
                className="mx-auto max-w-[92rem] px-5 sm:px-10 lg:px-14"
            >
                <div
                    data-contact-wrap
                    className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] lg:gap-16"
                >
                {/* Info & Contact Cards */}
                <div>
                    <Eyebrow className="text-[#E3A458]">{l("تواصل معنا", "Contact Us")}</Eyebrow>
                    <h2 className={`${H2} mt-3 text-[#FAF6F0]`}>
                        {l("جاهز تجرّب OralIQ", "Ready to Try OralIQ")}
                        <span className="mt-1.5 block text-[#E3A458]">
                            {l("أو تدمجها في منصتك؟", "Or Embed It in Your Platform?")}
                        </span>
                    </h2>
                    <p className="ar-body mt-4 sm:mt-5 max-w-xl text-base sm:text-lg font-medium leading-[1.85] text-[#FAF6F0]/85">
                        {l(
                            "سواء كنت دكتور جامعي عاوز تمتحن دفعتك شفوي أونلاين، أو إدارة مدرسة أو جامعة أو منصة تعليمية عاوزة تدمج الكويز الشفوي كـ فيتشر عندها، ابعتلنا وهنرتب معاك تجربة فورية.",
                            "Whether you're a lecturer looking to run online oral exams for your cohort, or a school, university, or LMS team ready to embed OralIQ as a feature, write to us and we'll set up a live trial.",
                        )}
                    </p>

                    <ul className="mt-8 sm:mt-9 space-y-3.5 sm:space-y-4">
                        <li
                            data-contact-card
                            className="flex items-center gap-4 rounded-[20px] sm:rounded-[22px] border border-white/20 bg-[#FAF6F0] p-4 sm:p-5 text-[#1C1410] shadow-lg"
                        >
                            <span className="flex size-11 sm:size-12 shrink-0 items-center justify-center rounded-2xl bg-[#6F4E37] text-[#FAF6F0]">
                                <Mail className="size-5" aria-hidden />
                            </span>
                            <div className="min-w-0">
                                <span className="block text-xs font-bold text-[#6F4E37]">
                                    {l("البريد الإلكتروني الرسمي", "Official Email")}
                                </span>
                                <a
                                    className="ltr block truncate font-display text-base sm:text-lg font-bold text-[#1C1410] hover:underline"
                                    href={`mailto:${COMPANY.email}`}
                                >
                                    {COMPANY.email}
                                </a>
                            </div>
                        </li>

                        {COMPANY.phone && (
                            <li
                                data-contact-card
                                className="flex items-center gap-4 rounded-[20px] sm:rounded-[22px] border border-white/20 bg-[#EFE7DE] p-4 sm:p-5 text-[#1C1410] shadow-lg"
                            >
                                <span className="flex size-11 sm:size-12 shrink-0 items-center justify-center rounded-2xl bg-[#38291F] text-[#FAF6F0]">
                                    <Phone className="size-5" aria-hidden />
                                </span>
                                <div>
                                    <span className="block text-xs font-bold text-[#6F4E37]">
                                        {l("الهاتف / واتساب", "Phone / WhatsApp")}
                                    </span>
                                    <a
                                        className="ltr block font-display text-base sm:text-lg font-bold tabular text-[#1C1410] hover:underline"
                                        href={telHref(COMPANY.phone)}
                                    >
                                        {COMPANY.phone}
                                    </a>
                                </div>
                            </li>
                        )}

                        {COMPANY.location.ar && (
                            <li
                                data-contact-card
                                className="flex items-center gap-4 rounded-[20px] sm:rounded-[22px] border border-white/20 bg-[#FAF6F0] p-4 sm:p-5 text-[#1C1410] shadow-lg"
                            >
                                <span className="flex size-11 sm:size-12 shrink-0 items-center justify-center rounded-2xl bg-[#6F4E37] text-[#FAF6F0]">
                                    <MapPin className="size-5" aria-hidden />
                                </span>
                                <div>
                                    <span className="block text-xs font-bold text-[#6F4E37]">
                                        {l("المقر", "Location")}
                                    </span>
                                    <span className="block font-display text-base sm:text-lg font-bold text-[#1C1410]">
                                        {l(COMPANY.location.ar, COMPANY.location.en)}
                                    </span>
                                </div>
                            </li>
                        )}
                    </ul>
                </div>

                {/* Editorial Contact Form Card */}
                <form
                    data-contact-card
                    onSubmit={submit}
                    className="grid gap-5 self-start rounded-[22px] sm:rounded-[26px] border border-rule bg-paper p-6 text-ink shadow-[0_28px_65px_-20px_rgba(0,0,0,0.45)] sm:p-10"
                    noValidate
                >
                    <div className="border-b border-rule pb-4">
                        <h3 className="ar-heading font-display text-xl sm:text-2xl font-bold text-ink">
                            {l("ابعتلنا رسالة سريعة", "Send Us a Quick Message")}
                        </h3>
                        <p className="ar-body mt-1 text-sm font-medium text-ink-2">
                            {l(
                                "اكتب بياناتك ونوع الجهة (جامعة / مدرسة / منصة تعليمية) وهنرد عليك فوراً.",
                                "Share your details and institution type (University / School / LMS) and we'll get right back to you.",
                            )}
                        </p>
                    </div>

                    {field(
                        "c-name",
                        l("الاسم بالكامل", "Full Name"),
                        <input
                            id="c-name"
                            name="name"
                            required
                            autoComplete="name"
                            placeholder={l("د. أحمد محمد / اسم المسؤول", "Dr. Ahmed / Contact name")}
                            aria-invalid={!!errors["c-name"] || undefined}
                            aria-describedby={errors["c-name"] ? "c-name-error" : undefined}
                            onChange={() => clear("c-name")}
                            className={FIELD}
                        />,
                    )}

                    {field(
                        "c-email",
                        l("البريد الإلكتروني", "Email Address"),
                        <input
                            id="c-email"
                            name="email"
                            type="email"
                            required
                            autoComplete="email"
                            dir="ltr"
                            placeholder="name@university.edu.eg"
                            aria-invalid={!!errors["c-email"] || undefined}
                            aria-describedby={errors["c-email"] ? "c-email-error" : undefined}
                            onChange={() => clear("c-email")}
                            className={cn(FIELD, "text-start")}
                        />,
                    )}

                    {field(
                        "c-message",
                        l("تفاصيل طلبك أو استفسارك", "Your Message"),
                        <textarea
                            id="c-message"
                            name="message"
                            required
                            rows={4}
                            placeholder={l(
                                "عاوز أجرب كويز شفوي في مادتي / عاوزين ندمج OralIQ كـ فيتشر جوه منصتنا التعليمية…",
                                "I want to try an oral quiz in my course / We want to embed OralIQ inside our platform…",
                            )}
                            aria-invalid={!!errors["c-message"] || undefined}
                            aria-describedby={errors["c-message"] ? "c-message-error" : undefined}
                            onChange={() => clear("c-message")}
                            className={cn(FIELD, "resize-y")}
                        />,
                    )}

                    <div className="flex flex-wrap items-center gap-4 pt-2">
                        <button type="submit" className={`${BTN} w-full sm:w-auto justify-center`}>
                            <Send className="size-4 rtl:-scale-x-100" aria-hidden />
                            {l("إرسال الرسالة", "Send Message")}
                        </button>
                        <p className="text-xs font-bold text-pen" aria-live="polite">
                            {sent
                                ? l("تم فتح برنامج البريد الإلكتروني بالرسالة جاهزة للإرسال.", "Your email app is open with the message ready to send.")
                                : l("رد سريع خلال 24 ساعة عمل.", "Fast response within 24 business hours.")}
                        </p>
                    </div>
                </form>
                </div>
            </div>
        </Section>
    );
}
