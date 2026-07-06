import type { HTMLAttributes } from "react";
import { twMerge } from "tailwind-merge";

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={twMerge("rounded-md border border-border bg-[#fffdf8] shadow-panel", className)}
      {...props}
    />
  );
}

