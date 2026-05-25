import { cn } from "@/lib/utils";
import { ButtonHTMLAttributes, forwardRef } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
}

const variants = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 shadow-sm",
  secondary: "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50",
  danger: "bg-red-600 text-white hover:bg-red-700",
  ghost: "text-slate-600 hover:bg-slate-100",
};

const sizes = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:opacity-50",
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    />
  )
);
Button.displayName = "Button";
