import type { ButtonHTMLAttributes } from "react";
import { twMerge } from "tailwind-merge";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
};

const variants = {
  primary: "bg-primary text-white shadow-sm hover:bg-teal-900",
  secondary: "bg-[#fffdf8] text-slate-800 border border-border hover:border-primary hover:bg-[#f8f4eb]",
  ghost: "text-slate-700 hover:bg-[#efe8dc]",
  danger: "bg-danger text-white hover:bg-red-700"
};

export function Button({ className, variant = "secondary", ...props }: ButtonProps) {
  return (
    <button
      className={twMerge(
        "inline-flex h-9 items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}

