/**
 * Product and company details, shown in the contact section, the footer and the auth pages.
 * Change them here only. Leave `phone` or `location` empty ("") to hide that line.
 *
 * OralIQ is the product; GharTech is the company that makes it (owner, 2026-10-23).
 */
export const COMPANY = {
    /** The product, and the name in the copyright line. */
    name: "OralIQ",
    /** The company behind it. */
    maker: "GharTech",
    email: "ghartech1@gmail.com",
    /** International format; the page builds the tel: link from it. */
    phone: "+20 106 540 7502",
    location: { ar: "المنصورة، مصر", en: "Mansoura, Egypt" },
};

/** "+20 106 540 7502" → "tel:+201065407502" */
export const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;
