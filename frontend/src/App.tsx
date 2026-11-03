import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { DashboardLayout } from "./layouts/DashboardLayout";
import PrivateRoute from "./components/PrivateRoute";
import { PageLoader } from "./components/PageLoader";
import { SmoothScroll } from "./components/SmoothScroll";
import LandingPage from "./pages/LandingPage";

const LoginPage = lazy(() => import("./pages/Login"));
const RegisterPage = lazy(() => import("./pages/Register"));
const VerifyEmail = lazy(() => import("./pages/VerifyEmail"));
const ExamInvite = lazy(() => import("./pages/ExamInvite"));
const ExamRoom = lazy(() => import("./pages/ExamRoom"));
const Overview = lazy(() => import("./pages/Overview"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const LecturerResults = lazy(() => import("./pages/LecturerResults"));
const StudentsPage = lazy(() => import("./pages/StudentsPage"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage"));
const AttendancePage = lazy(() => import("./pages/AttendancePage"));
const Settings = lazy(() => import("./pages/Settings"));
const MyGrades = lazy(() => import("./pages/MyGrades"));
const MessagesPage = lazy(() => import("./pages/MessagesPage"));
const NotFound = lazy(() => import("./pages/NotFound"));

function App() {
    return (
        <Suspense fallback={<PageLoader fullscreen />}>
            <SmoothScroll />
            <Routes>
                {/* Public */}
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/verify-email" element={<VerifyEmail />} />
                <Route path="/" element={<LandingPage />} />

                {/* Exam invite link — saves token, redirects to login or dashboard */}
                <Route path="/exam/:token" element={<ExamInvite />} />

                {/* Actual exam flow (requires login) */}
                <Route path="/exam/start" element={<ExamRoom />} />

                {/* Dashboard — requires auth */}
                <Route element={<PrivateRoute />}>
                    <Route element={<DashboardLayout />}>
                        <Route path="/dashboard" element={<Suspense fallback={<PageLoader />}><Overview /></Suspense>} />
                        <Route path="/dashboard/questions" element={<Suspense fallback={<PageLoader />}><Dashboard /></Suspense>} />
                        <Route path="/dashboard/interview/:questionId" element={<Navigate to="/dashboard" replace />} />
                        <Route path="/dashboard/results" element={<Suspense fallback={<PageLoader />}><LecturerResults /></Suspense>} />
                        <Route path="/dashboard/students" element={<Suspense fallback={<PageLoader />}><StudentsPage /></Suspense>} />
                        <Route path="/dashboard/analytics" element={<Suspense fallback={<PageLoader />}><AnalyticsPage /></Suspense>} />
                        <Route path="/dashboard/attendance" element={<Suspense fallback={<PageLoader />}><AttendancePage /></Suspense>} />
                        <Route path="/dashboard/settings" element={<Suspense fallback={<PageLoader />}><Settings /></Suspense>} />
                        <Route path="/dashboard/grades" element={<Suspense fallback={<PageLoader />}><MyGrades /></Suspense>} />
                        <Route path="/dashboard/messages" element={<Suspense fallback={<PageLoader />}><MessagesPage /></Suspense>} />
                    </Route>
                </Route>

                <Route path="*" element={<NotFound />} />
            </Routes>
        </Suspense>
    );
}

export default App;
