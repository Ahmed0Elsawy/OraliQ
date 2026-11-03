import * as React from "react";
import { Eye, EyeOff, Lock } from "lucide-react";
import { Input, type InputProps } from "./input";
import { useI18n } from "../../i18n";

export const PasswordInput = React.forwardRef<HTMLInputElement, Omit<InputProps, "type" | "icon">>((props, ref) => {
    const [visible, setVisible] = React.useState(false);
    const { l } = useI18n();
    return (
        <div className="relative">
            <Input ref={ref} type={visible ? "text" : "password"} icon={<Lock />} trailing {...props} />
            <button
                type="button"
                onClick={() => setVisible((v) => !v)}
                aria-label={visible ? l("إخفاء كلمة المرور", "Hide password") : l("إظهار كلمة المرور", "Show password")}
                aria-pressed={visible}
                className="absolute inset-y-0 end-1.5 my-auto flex size-9 items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-pen-wash hover:text-ink"
            >
                {visible ? <EyeOff className="size-5" aria-hidden /> : <Eye className="size-5" aria-hidden />}
            </button>
        </div>
    );
});
PasswordInput.displayName = "PasswordInput";
