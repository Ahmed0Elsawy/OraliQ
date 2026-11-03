import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../lib/api";
import { PageLoader } from "../components/PageLoader";

/**
 * ExamInvite — handles the shared exam link.
 * Saves the exam token, then only lets an authenticated student enter.
 * Old lecturer/expired sessions are cleared so the student signup flow is shown.
 */
export default function ExamInvite() {
    const { token } = useParams<{ token: string }>();
    const navigate = useNavigate();

    useEffect(() => {
        let cancelled = false;

        if (token) {
            // Save pending exam token so the exam room can pick it up
            localStorage.setItem("pendingExamToken", token);
        }

        const goToStudentSignup = () => {
            localStorage.removeItem("token");
            navigate("/register?redirect=/exam/start&role=student", { replace: true });
        };

        const resolveInvite = async () => {
            const authToken = localStorage.getItem("token");
            if (!authToken) {
                goToStudentSignup();
                return;
            }

            try {
                const { data } = await api.get("/users/me");
                if (cancelled) return;

                if (data?.role === "student") {
                    navigate("/exam/start", { replace: true });
                    return;
                }

                // A lecturer/admin token on the student's device should not skip signup.
                goToStudentSignup();
            } catch {
                if (!cancelled) goToStudentSignup();
            }
        };

        resolveInvite();
        return () => { cancelled = true; };
    }, [token, navigate]);

    // Brief loading state while redirecting
    return <PageLoader fullscreen />;
}
