# Photo credits

All photos are from [Unsplash](https://unsplash.com) under the
[Unsplash License](https://unsplash.com/license) (free for commercial use, no attribution required).
Credited here anyway, as good practice.

Every photo of a person on the site is one series: the same young man, photographed by
**Seyed Ali Mousavi Noor** (https://unsplash.com/@seyed_ali_mousavi_noor), shown in black and white with
one shared tone (levels, a slight midtone lift, light contrast). One series keeps the site reading as one
piece instead of a collage of stock photos.

| File | Where | Source |
|------|-------|--------|
| face-light-*.webp, face-dark-*.webp | Home hero, light and dark (cut out) | https://unsplash.com/photos/6p1yr-vnVFw |
| about-student-*.webp, overview-student-*.webp | Home "who we are"; student overview | https://unsplash.com/photos/vc7D2UYyINw |
| video-cover-*.webp | Home video banner | https://unsplash.com/photos/d0EO6tAoRvI |
| auth-signin-*.webp | Sign-in page | https://unsplash.com/photos/IJhuT1YqZ-M |
| auth-signup-*.webp | Sign-up page | https://unsplash.com/photos/d0EO6tAoRvI |
| exam-student-*.webp | Exam room | https://unsplash.com/photos/rUQUhU4oGHU |
| grades-student-*.webp | Student grades | https://unsplash.com/photos/mceilTptrMM |

Small edits: the hero portrait is cut out with MediaPipe Selfie Segmentation (edges refined with a guided
filter), a small brand mark on its shirt is painted out, and the ends of the shoulders fade into the page.
Crops avoid printed text on clothing.

The face mesh drawn over the hero portrait is MediaPipe FaceMesh (refineLandmarks, 478 points) run on that
photo, the same model the exam room uses (`src/components/home/faceMesh.ts`).

The explainer video (`/media/oraliq-demo.mp4`) is a screen recording of the app with demo data; the
student's camera in it shows the exam-room photo of the same series (rUQUhU4oGHU, webcam framing).
