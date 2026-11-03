import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Language = "ar" | "en";

type TranslationKey =
    | "language.toggle"
    | "auth.signIn.title"
    | "auth.signIn.subtitle"
    | "auth.email"
    | "auth.password"
    | "auth.fullName"
    | "auth.signIn.button"
    | "auth.signIn.loading"
    | "auth.signUp.link"
    | "auth.noAccount"
    | "auth.hasAccount"
    | "auth.create.title"
    | "auth.create.subtitle"
    | "auth.create.studentInvite"
    | "auth.create.button"
    | "auth.create.loading"
    | "auth.role.label"
    | "auth.role.student"
    | "auth.role.studentSub"
    | "auth.role.lecturer"
    | "auth.role.lecturerSub"
    | "auth.invalidLogin"
    | "auth.registerFailed"
    | "auth.hero.title1"
    | "auth.hero.title2"
    | "auth.hero.title3"
    | "auth.hero.description"
    | "auth.hero.speech"
    | "auth.hero.nlp"
    | "auth.hero.integrity"
    | "nav.overview"
    | "nav.questions"
    | "nav.results"
    | "nav.students"
    | "nav.analytics"
    | "nav.attendance"
    | "nav.settings"
    | "nav.grades"
    | "nav.messages"
    | "nav.signOut"
    | "nav.platform"
    | "nav.account"
    | "dashboard.questions.title"
    | "dashboard.questions.subtitle"
    | "dashboard.questions.new"
    | "dashboard.questions.emptyTitle"
    | "dashboard.questions.emptySubtitle"
    | "dashboard.questions.question"
    | "dashboard.questions.answer"
    | "dashboard.questions.keywords"
    | "dashboard.questions.category"
    | "dashboard.questions.difficulty"
    | "dashboard.questions.duration"
    | "dashboard.questions.cancel"
    | "dashboard.questions.create"
    | "dashboard.questions.creating"
    | "dashboard.questions.copy"
    | "dashboard.questions.copied"
    | "dashboard.questions.assign"
    | "dashboard.questions.assignTitle"
    | "dashboard.questions.searchStudents"
    | "dashboard.questions.noStudents"
    | "dashboard.questions.done"
    | "overview.lecturerTitle"
    | "overview.studentTitle"
    | "overview.welcome"
    | "overview.examsCreated"
    | "overview.submissions"
    | "overview.avgScore"
    | "overview.pendingAi"
    | "overview.myExams"
    | "overview.startExam"
    | "messages.title"
    | "messages.none"
    | "messages.loading"
    | "messages.emptyTitle"
    | "messages.emptyStudent"
    | "messages.emptyDefault"
    | "messages.inviteTitle"
    | "messages.startExam"
    | "messages.justNow"
    | "exam.badge"
    | "exam.welcome"
    | "exam.info"
    | "exam.namePlaceholder"
    | "exam.idPlaceholder"
    | "exam.needData"
    | "exam.noQuestion"
    | "exam.permission"
    | "exam.ruleMic"
    | "exam.ruleCamera"
    | "exam.ruleNoPhone"
    | "exam.beginExam"
    | "exam.start"
    | "exam.previewHint"
    | "exam.question"
    | "exam.recording"
    | "exam.stop"
    | "exam.processing"
    | "exam.failed"
    | "exam.sessionExpired"
    | "exam.backDashboard"
    | "exam.done"
    | "exam.finalScore"
    | "exam.content"
    | "exam.fluency"
    | "exam.integrity"
    | "grades.title"
    | "grades.subtitle"
    | "grades.loading"
    | "grades.emptyTitle"
    | "grades.emptySubtitle"
    | "settings.title"
    | "settings.subtitle"
    | "settings.profile"
    | "settings.upload"
    | "settings.choosePhoto"
    | "settings.accountInfo"
    | "settings.save"
    | "settings.saved";

const translations: Record<Language, Record<TranslationKey, string>> = {
    ar: {
        "language.toggle": "English",
        "auth.signIn.title": "تسجيل الدخول",
        "auth.signIn.subtitle": "ادخل إلى لوحة التحكم",
        "auth.email": "البريد الإلكتروني",
        "auth.password": "كلمة المرور",
        "auth.fullName": "الاسم الكامل",
        "auth.signIn.button": "تسجيل الدخول",
        "auth.signIn.loading": "جاري الدخول...",
        "auth.signUp.link": "إنشاء حساب",
        "auth.noAccount": "ليس لديك حساب؟",
        "auth.hasAccount": "لديك حساب بالفعل؟",
        "auth.create.title": "إنشاء حساب",
        "auth.create.subtitle": "انضم إلى OralIQ وابدأ رحلتك",
        "auth.create.studentInvite": "تمت دعوتك لامتحان. أنشئ حساب طالب للمتابعة.",
        "auth.create.button": "إنشاء الحساب",
        "auth.create.loading": "جاري إنشاء الحساب...",
        "auth.role.label": "أنا...",
        "auth.role.student": "طالب",
        "auth.role.studentSub": "أداء الامتحانات",
        "auth.role.lecturer": "محاضر",
        "auth.role.lecturerSub": "إعداد الامتحانات",
        "auth.invalidLogin": "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
        "auth.registerFailed": "فشل إنشاء الحساب. حاول مرة أخرى.",
        "auth.hero.title1": "منصة",
        "auth.hero.title2": "امتحانات",
        "auth.hero.title3": "ذكية",
        "auth.hero.description": "أدر امتحانات شفوية مدعومة بالذكاء الاصطناعي مع تحليل الصوت، تقييم الإجابة، ومراقبة النزاهة.",
        "auth.hero.speech": "تعرف صوتي وتحليل طلاقة الكلام",
        "auth.hero.nlp": "تقييم الإجابات بالذكاء الاصطناعي",
        "auth.hero.integrity": "مراقبة الوجه وسلوك الغش",
        "nav.overview": "نظرة عامة",
        "nav.questions": "أسئلة الامتحان",
        "nav.results": "النتائج",
        "nav.students": "الطلاب",
        "nav.analytics": "التحليلات",
        "nav.attendance": "الحضور",
        "nav.settings": "الإعدادات",
        "nav.grades": "درجاتي",
        "nav.messages": "الرسائل",
        "nav.signOut": "تسجيل الخروج",
        "nav.platform": "المنصة",
        "nav.account": "الحساب",
        "dashboard.questions.title": "أسئلة الامتحان",
        "dashboard.questions.subtitle": "كل سؤال له رابط مشاركة خاص",
        "dashboard.questions.new": "سؤال جديد",
        "dashboard.questions.emptyTitle": "لا توجد أسئلة بعد",
        "dashboard.questions.emptySubtitle": "أنشئ أول سؤال امتحان.",
        "dashboard.questions.question": "السؤال",
        "dashboard.questions.answer": "الإجابة النموذجية",
        "dashboard.questions.keywords": "الكلمات المفتاحية",
        "dashboard.questions.category": "التصنيف",
        "dashboard.questions.difficulty": "الصعوبة",
        "dashboard.questions.duration": "المدة بالدقائق",
        "dashboard.questions.cancel": "إلغاء",
        "dashboard.questions.create": "إنشاء والحصول على الرابط",
        "dashboard.questions.creating": "جاري الإنشاء...",
        "dashboard.questions.copy": "نسخ",
        "dashboard.questions.copied": "تم النسخ",
        "dashboard.questions.assign": "إرسال",
        "dashboard.questions.assignTitle": "إرسال لطالب",
        "dashboard.questions.searchStudents": "ابحث عن طالب...",
        "dashboard.questions.noStudents": "لا يوجد طلاب.",
        "dashboard.questions.done": "تم",
        "overview.lecturerTitle": "نظرة عامة على المنصة",
        "overview.studentTitle": "امتحاناتي",
        "overview.welcome": "مرحباً",
        "overview.examsCreated": "الامتحانات المنشأة",
        "overview.submissions": "الإجابات",
        "overview.avgScore": "متوسط الدرجة",
        "overview.pendingAi": "قيد التصحيح",
        "overview.myExams": "امتحاناتي",
        "overview.startExam": "ابدأ الامتحان",
        "messages.title": "الرسائل",
        "messages.none": "لا توجد رسائل جديدة",
        "messages.loading": "جاري تحميل الرسائل...",
        "messages.emptyTitle": "لا توجد رسائل",
        "messages.emptyStudent": "عندما يرسل لك المحاضر امتحاناً سيظهر هنا.",
        "messages.emptyDefault": "لا توجد إشعارات حالياً.",
        "messages.inviteTitle": "دعوة امتحان جديدة",
        "messages.startExam": "ابدأ الامتحان",
        "messages.justNow": "الآن",
        "exam.badge": "امتحان شفوي",
        "exam.welcome": "أهلاً بيك",
        "exam.info": "دخل بياناتك ثم اضغط بدء الامتحان لفتح الكاميرا. السؤال والمراقبة يظهروا لما تضغط ابدأ التسجيل.",
        "exam.namePlaceholder": "الاسم الكامل",
        "exam.idPlaceholder": "رقم الطالب",
        "exam.needData": "لازم تدخل اسمك ورقمك الأول.",
        "exam.noQuestion": "مفيش سؤال متاح.",
        "exam.permission": "محتاج إذن الكاميرا والميكروفون.",
        "exam.ruleMic": "اتكلم بصوت واضح وقريب من الميك",
        "exam.ruleCamera": "بص في الكاميرا أثناء الإجابة",
        "exam.ruleNoPhone": "مفيش موبايل أو ملاحظات معاك",
        "exam.beginExam": "بدء الامتحان",
        "exam.start": "ابدأ التسجيل",
        "exam.previewHint": "اتأكد إن وجهك ظاهر في الكاميرا، ثم اضغط ابدأ التسجيل لبدء الامتحان.",
        "exam.question": "السؤال",
        "exam.recording": "جاري التسجيل، اضغط لما تخلص",
        "exam.stop": "أنه الإجابة وأرسل",
        "exam.processing": "جاري التحليل والتصحيح...",
        "exam.failed": "فشل إرسال الامتحان",
        "exam.sessionExpired": "انتهت جلسة الدخول. سجل دخولك مرة أخرى من نفس رابط الامتحان ثم أعد المحاولة.",
        "exam.backDashboard": "العودة للوحة التحكم",
        "exam.done": "تم إرسال الإجابة",
        "exam.finalScore": "الدرجة النهائية",
        "exam.content": "المحتوى",
        "exam.fluency": "الطلاقة",
        "exam.integrity": "النزاهة",
        "grades.title": "درجاتي",
        "grades.subtitle": "الامتحانات المكتملة التي نشرها المحاضر",
        "grades.loading": "جاري تحميل النتائج...",
        "grades.emptyTitle": "لا توجد درجات منشورة",
        "grades.emptySubtitle": "ستظهر الامتحانات المكتملة هنا بعد اعتماد ونشر الدرجات.",
        "settings.title": "الإعدادات",
        "settings.subtitle": "إدارة الحساب والتفضيلات",
        "settings.profile": "الصورة الشخصية",
        "settings.upload": "ارفع صورة جديدة",
        "settings.choosePhoto": "اختيار صورة",
        "settings.accountInfo": "بيانات الحساب",
        "settings.save": "حفظ التغييرات",
        "settings.saved": "تم حفظ التغييرات بنجاح",
    },
    en: {
        "language.toggle": "العربية",
        "auth.signIn.title": "Sign in",
        "auth.signIn.subtitle": "Continue to your dashboard",
        "auth.email": "Email address",
        "auth.password": "Password",
        "auth.fullName": "Full name",
        "auth.signIn.button": "Sign In",
        "auth.signIn.loading": "Signing in...",
        "auth.signUp.link": "Sign up",
        "auth.noAccount": "Don't have an account?",
        "auth.hasAccount": "Already have an account?",
        "auth.create.title": "Create account",
        "auth.create.subtitle": "Join OralIQ and start your journey",
        "auth.create.studentInvite": "You've been invited to take an exam. Create a student account to continue.",
        "auth.create.button": "Create Account",
        "auth.create.loading": "Creating account...",
        "auth.role.label": "I am a...",
        "auth.role.student": "Student",
        "auth.role.studentSub": "Take exams",
        "auth.role.lecturer": "Lecturer",
        "auth.role.lecturerSub": "Set exams",
        "auth.invalidLogin": "Invalid email or password. Please try again.",
        "auth.registerFailed": "Registration failed. Please try again.",
        "auth.hero.title1": "AI Oral",
        "auth.hero.title2": "Exam",
        "auth.hero.title3": "Platform",
        "auth.hero.description": "Conduct AI-powered oral exams with speech recognition, answer grading, and integrity monitoring.",
        "auth.hero.speech": "Real-time speech recognition and fluency scoring",
        "auth.hero.nlp": "AI evaluates answer quality and relevance",
        "auth.hero.integrity": "Facial analysis with anti-cheat checks",
        "nav.overview": "Overview",
        "nav.questions": "Exam Questions",
        "nav.results": "Results",
        "nav.students": "Students",
        "nav.analytics": "Analytics",
        "nav.attendance": "Attendance",
        "nav.settings": "Settings",
        "nav.grades": "My Grades",
        "nav.messages": "Messages",
        "nav.signOut": "Sign out",
        "nav.platform": "Platform",
        "nav.account": "Account",
        "dashboard.questions.title": "Exam Questions",
        "dashboard.questions.subtitle": "Each question has a unique shareable link",
        "dashboard.questions.new": "New Question",
        "dashboard.questions.emptyTitle": "No questions yet",
        "dashboard.questions.emptySubtitle": "Create your first exam question.",
        "dashboard.questions.question": "Question",
        "dashboard.questions.answer": "Model Answer",
        "dashboard.questions.keywords": "Keywords",
        "dashboard.questions.category": "Category",
        "dashboard.questions.difficulty": "Difficulty",
        "dashboard.questions.duration": "Duration (Minutes)",
        "dashboard.questions.cancel": "Cancel",
        "dashboard.questions.create": "Create & Get Link",
        "dashboard.questions.creating": "Creating...",
        "dashboard.questions.copy": "Copy",
        "dashboard.questions.copied": "Copied",
        "dashboard.questions.assign": "Assign",
        "dashboard.questions.assignTitle": "Assign to Student",
        "dashboard.questions.searchStudents": "Search students...",
        "dashboard.questions.noStudents": "No students found.",
        "dashboard.questions.done": "Done",
        "overview.lecturerTitle": "Platform Overview",
        "overview.studentTitle": "My Exams",
        "overview.welcome": "Welcome back",
        "overview.examsCreated": "Exams Created",
        "overview.submissions": "Submissions",
        "overview.avgScore": "Avg Score",
        "overview.pendingAi": "Pending AI",
        "overview.myExams": "My Exams",
        "overview.startExam": "Start Exam",
        "messages.title": "Messages",
        "messages.none": "No new messages",
        "messages.loading": "Loading messages...",
        "messages.emptyTitle": "All caught up!",
        "messages.emptyStudent": "When your professor assigns you an exam, it will appear here.",
        "messages.emptyDefault": "No new notifications at this time.",
        "messages.inviteTitle": "New Exam Invitation",
        "messages.startExam": "Start Exam",
        "messages.justNow": "Just now",
        "exam.badge": "Oral Exam",
        "exam.welcome": "Welcome",
        "exam.info": "Enter your details, then start the exam to open the camera. The question and monitoring appear when you press Start recording.",
        "exam.namePlaceholder": "Full name",
        "exam.idPlaceholder": "Student number",
        "exam.needData": "Please enter your name and student number first.",
        "exam.noQuestion": "No question is available.",
        "exam.permission": "Camera and microphone permission is required.",
        "exam.ruleMic": "Speak clearly near the microphone",
        "exam.ruleCamera": "Look at the camera while answering",
        "exam.ruleNoPhone": "No phone or notes with you",
        "exam.beginExam": "Start exam",
        "exam.start": "Start recording",
        "exam.previewHint": "Make sure your face is visible, then press Start recording to begin the exam.",
        "exam.question": "Question",
        "exam.recording": "Recording, press when finished",
        "exam.stop": "Finish and submit",
        "exam.processing": "Analyzing and grading...",
        "exam.failed": "Exam submission failed",
        "exam.sessionExpired": "Your login session expired. Sign in again from the same exam link, then try again.",
        "exam.backDashboard": "Back to dashboard",
        "exam.done": "Answer submitted",
        "exam.finalScore": "Final Score",
        "exam.content": "Content",
        "exam.fluency": "Fluency",
        "exam.integrity": "Integrity",
        "grades.title": "My Grades",
        "grades.subtitle": "Completed assessments released by your professor",
        "grades.loading": "Fetching your results...",
        "grades.emptyTitle": "No Grades Published",
        "grades.emptySubtitle": "Completed exams will appear here once final scores are published.",
        "settings.title": "Settings",
        "settings.subtitle": "Manage your account and preferences",
        "settings.profile": "Profile Picture",
        "settings.upload": "Upload a new photo",
        "settings.choosePhoto": "Choose Photo",
        "settings.accountInfo": "Account Information",
        "settings.save": "Save Changes",
        "settings.saved": "Changes saved successfully!",
    },
};

type I18nContextValue = {
    lang: Language;
    dir: "rtl" | "ltr";
    setLang: (lang: Language) => void;
    toggleLang: () => void;
    t: (key: TranslationKey) => string;
    /** Inline bilingual text for one-off strings: l("نص", "Text"). */
    l: (ar: string, en: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
    const [lang, setLangState] = useState<Language>(() => {
        // No storage while the home page is rendered at build time (or in a locked-down browser)
        let saved: string | null = null;
        try { saved = localStorage.getItem("oraliq_lang"); } catch { /* default to Arabic */ }
        return saved === "en" ? "en" : "ar";
    });

    const dir = lang === "ar" ? "rtl" : "ltr";

    const setLang = (nextLang: Language) => {
        setLangState(nextLang);
        localStorage.setItem("oraliq_lang", nextLang);
    };

    useEffect(() => {
        document.documentElement.lang = lang;
        document.documentElement.dir = dir;
    }, [dir, lang]);

    const value = useMemo<I18nContextValue>(() => ({
        lang,
        dir,
        setLang,
        toggleLang: () => setLang(lang === "ar" ? "en" : "ar"),
        t: (key) => translations[lang][key] ?? translations.en[key] ?? key,
        l: (ar, en) => (lang === "ar" ? ar : en),
    }), [dir, lang]);

    return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
    const context = useContext(I18nContext);
    if (!context) {
        throw new Error("useI18n must be used inside I18nProvider");
    }
    return context;
}
