/** Client helpers: capture frames → InsightFace / MobileGaze on the server (no browser face model). */

export const EMBEDDING_DIM = 512; // InsightFace ArcFace

function sleep(ms: number) {
    return new Promise((r) => setTimeout(r, ms));
}

/** Grab a JPEG snapshot from a live video element */
export async function captureVideoJpeg(
    video: HTMLVideoElement,
    quality = 0.72,
    maxSide = 640,
): Promise<Blob> {
    if (video.readyState < 2) {
        throw new Error("الكاميرا لسه مش جاهزة");
    }
    const vw = video.videoWidth || 640;
    const vh = video.videoHeight || 480;
    const scale = Math.min(1, maxSide / Math.max(vw, vh));
    const w = Math.max(1, Math.round(vw * scale));
    const h = Math.max(1, Math.round(vh * scale));

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas unavailable");
    ctx.drawImage(video, 0, 0, w, h);

    const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob((b) => resolve(b), "image/jpeg", quality),
    );
    if (!blob) throw new Error("فشل التقاط صورة الوجه");
    return blob;
}

/** Capture several frames for InsightFace enrollment (uploaded as multipart) */
export async function buildFaceEnrollForm(
    video: HTMLVideoElement,
    samples = 5,
    intervalMs = 380,
): Promise<FormData> {
    const fd = new FormData();
    let ok = 0;
    for (let i = 0; i < samples; i++) {
        await sleep(intervalMs);
        try {
            const blob = await captureVideoJpeg(video, 0.78, 720);
            fd.append("images", blob, `face_${i}.jpg`);
            ok += 1;
        } catch {
            /* skip bad frame */
        }
    }
    if (ok < 3) {
        throw new Error("لم نتمكن من قراءة وجهك — تأكد أن وجهك ظاهر في الكاميرا");
    }
    return fd;
}

/**
 * One frame for POST /face/verify. With examToken the server records the check for that exam,
 * and the answer's face score is computed from those records (the browser never sends a score).
 */
export async function buildFaceVerifyForm(video: HTMLVideoElement, examToken?: string): Promise<FormData> {
    const fd = new FormData();
    const blob = await captureVideoJpeg(video, 0.7, 640);
    fd.append("image", blob, "verify.jpg");
    if (examToken) fd.append("exam_token", examToken);
    return fd;
}

export async function buildGazeForm(
    video: HTMLVideoElement,
    normalizedFaceBox?: number[] | null,
): Promise<FormData> {
    const fd = new FormData();
    const blob = await captureVideoJpeg(video, 0.65, 480);
    fd.append("image", blob, "gaze.jpg");
    if (normalizedFaceBox?.length === 4) {
        fd.append("bbox", JSON.stringify(normalizedFaceBox));
    }
    return fd;
}

/** Drop worst frames — average the rest (Face ID scores 0–100) */
export function aggregateFaceScores(scores: number[]): number {
    if (scores.length === 0) return 0;
    if (scores.length === 1) return scores[0];
    const sorted = [...scores].sort((x, y) => x - y);
    const drop = Math.max(1, Math.floor(sorted.length * 0.25));
    const kept = sorted.slice(drop);
    return kept.reduce((a, b) => a + b, 0) / kept.length;
}
