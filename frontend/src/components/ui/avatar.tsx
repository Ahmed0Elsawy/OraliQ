import * as React from "react";
import { cn } from "@/lib/utils";

const sizes = { sm: "size-8 text-xs", md: "size-10 text-sm", lg: "size-14 text-lg" };

// Stable warm tint per name, so the same person always gets the same warm espresso/amber colour.
const tints = ["bg-pen-wash text-pen", "bg-sun-wash text-sun", "bg-teal-wash text-teal", "bg-warn-wash text-warn", "bg-pass-wash text-pass"];
function tintFor(name?: string | null) {
    let h = 0;
    for (const ch of name || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return tints[h % tints.length];
}

/** First letter of the first two words: "د. سلمى عبد" → "سع" (skips titles like "د."). */
function initials(name?: string | null) {
    const words = (name || "").split(/\s+/).filter((w) => w && !w.endsWith("."));
    return words.slice(0, 2).map((w) => w[0]).join("") || "؟";
}

const AvatarContext = React.createContext<{ imgLoaded: boolean; setImgLoaded: (v: boolean) => void }>({
    imgLoaded: false,
    setImgLoaded: () => {},
});

export interface AvatarProps extends React.HTMLAttributes<HTMLSpanElement> {
    name?: string | null;
    src?: string | null;
    size?: keyof typeof sizes;
}

export const Avatar = React.forwardRef<HTMLSpanElement, AvatarProps>(
    ({ name, src, size = "md", className, children, ...props }, ref) => {
        const [imgLoaded, setImgLoaded] = React.useState(false);

        // If used with shadcn children (<Avatar><AvatarImage /><AvatarFallback /></Avatar>)
        if (children) {
            return (
                <AvatarContext.Provider value={{ imgLoaded, setImgLoaded }}>
                    <span
                        ref={ref}
                        className={cn(
                            "relative flex h-10 w-10 shrink-0 overflow-hidden rounded-full",
                            className,
                        )}
                        {...props}
                    >
                        {children}
                    </span>
                </AvatarContext.Provider>
            );
        }

        // Existing Dashboard usage (<Avatar name={...} src={...} size={...} />)
        return (
            <span
                ref={ref}
                className={cn(
                    "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-display font-semibold",
                    tintFor(name),
                    sizes[size],
                    className,
                )}
                aria-hidden
                {...props}
            >
                {src ? <img src={src} alt="" className="size-full object-cover" /> : initials(name)}
            </span>
        );
    },
);
Avatar.displayName = "Avatar";

export const AvatarImage = React.forwardRef<
    HTMLImageElement,
    React.ImgHTMLAttributes<HTMLImageElement>
>(({ className, src, alt = "", onLoad, onError, ...props }, ref) => {
    const { imgLoaded, setImgLoaded } = React.useContext(AvatarContext);
    const [failed, setFailed] = React.useState(false);

    if (!src || failed) return null;

    return (
        <img
            ref={ref}
            src={src}
            alt={alt}
            onLoad={(e) => {
                setImgLoaded(true);
                onLoad?.(e);
            }}
            onError={(e) => {
                setFailed(true);
                setImgLoaded(false);
                onError?.(e);
            }}
            className={cn("aspect-square h-full w-full object-cover", !imgLoaded && "hidden", className)}
            {...props}
        />
    );
});
AvatarImage.displayName = "AvatarImage";

export const AvatarFallback = React.forwardRef<
    HTMLSpanElement,
    React.HTMLAttributes<HTMLSpanElement>
>(({ className, children, ...props }, ref) => {
    const { imgLoaded } = React.useContext(AvatarContext);
    if (imgLoaded) return null;

    return (
        <span
            ref={ref}
            className={cn(
                "flex h-full w-full items-center justify-center rounded-full bg-pen-wash font-display text-xs font-extrabold text-pen",
                className,
            )}
            {...props}
        >
            {children}
        </span>
    );
});
AvatarFallback.displayName = "AvatarFallback";

export default Avatar;
