"use client";

import React, { forwardRef } from "react";
import { Loader2 } from "lucide-react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger" | "subtle";
  size?: "sm" | "md" | "lg" | "icon";
  isLoading?: boolean;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  icon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      variant = "primary",
      size = "md",
      isLoading = false,
      loading = false,
      leftIcon,
      icon,
      rightIcon,
      className = "",
      disabled,
      ...props
    },
    ref
  ) => {
    const isBusy = isLoading || loading;
    const resolvedLeftIcon = leftIcon || icon;
    const baseStyles =
      "inline-flex items-center justify-center font-medium transition-all duration-150 rounded-lg select-none focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-950 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]";

    const variantStyles = {
      primary:
        "bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold shadow-md shadow-cyan-500/20 focus:ring-cyan-400 border border-cyan-400/40",
      secondary:
        "bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-700 focus:ring-slate-400",
      outline:
        "bg-transparent hover:bg-slate-800/60 text-slate-200 border border-slate-700/80 hover:border-slate-600 focus:ring-slate-400",
      ghost:
        "bg-transparent hover:bg-slate-800/50 text-slate-300 hover:text-white focus:ring-slate-400",
      danger:
        "bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/20 focus:ring-rose-500 border border-rose-500/40",
      subtle:
        "bg-cyan-950/40 hover:bg-cyan-900/50 text-cyan-300 border border-cyan-800/40 focus:ring-cyan-500",
    };

    const sizeStyles = {
      sm: "text-xs px-2.5 py-1.5 gap-1.5",
      md: "text-xs px-3.5 py-2 gap-2",
      lg: "text-sm px-4 py-2.5 gap-2.5",
      icon: "p-2 w-8 h-8",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isBusy}
        className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
        {...props}
      >
        {isBusy ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-current shrink-0" />
        ) : (
          resolvedLeftIcon
        )}
        {children}
        {!isBusy && rightIcon}
      </button>
    );
  }
);

Button.displayName = "Button";
