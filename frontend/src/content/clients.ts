/**
 * Institutions that use OralIQ, shown on the home page.
 *
 * Add real clients only. Each entry needs a name in both languages; a logo is recommended
 * (put the file in /public/clients/ and reference it as "/clients/<file>").
 *
 *   { name: { ar: "اسم العميل", en: "Client name" }, logo: "/clients/client.svg", href: "https://example.com" },
 *
 * While this list is empty, the home page shows labelled placeholder slots on the
 * development server only, and hides the section in production, so a visitor never
 * sees invented clients.
 */

export interface Client {
    name: { ar: string; en: string };
    logo?: string;
    /** The client's website, if they agreed to be linked. */
    href?: string;
}

export const CLIENTS: Client[] = [];
