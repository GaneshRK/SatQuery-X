"use client";

import React from "react";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "danger" | "info" | "outline" | "satellite" | "cyan";
  size?: "sm" | "md";
  dot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = "default",
  size = "md",
  dot = false,
  className = "",
  ...props
}) => {
  const variantStyles = {
    default: "bg-slate-800/80 text-slate-300 border-slate-700/60",
    success: "bg-emerald-950/40 text-emerald-300 border-emerald-800/40",
    warning: "bg-amber-950/40 text-amber-300 border-amber-800/40",
    danger: "bg-rose-950/40 text-rose-300 border-rose-800/40",
    info: "bg-cyan-950/40 text-cyan-300 border-cyan-800/40",
    cyan: "bg-cyan-950/40 text-cyan-300 border-cyan-800/40",
    outline: "bg-transparent text-slate-300 border-slate-700",
    satellite: "bg-blue-950/50 text-blue-300 border-blue-700/50 font-mono tracking-tight",
  };

  const dotColors = {
    default: "bg-slate-400",
    success: "bg-emerald-400",
    warning: "bg-amber-400",
    danger: "bg-rose-400",
    info: "bg-cyan-400",
    cyan: "bg-cyan-400",
    outline: "bg-slate-400",
    satellite: "bg-blue-400 animate-pulse",
  };

  const sizeStyles = {
    sm: "text-[10px] px-1.5 py-0.5 gap-1",
    md: "text-xs px-2.5 py-0.5 gap-1.5",
  };

  return (
    <span
      className={`inline-flex items-center font-medium border rounded-md select-none ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColors[variant]}`} />}
      {children}
    </span>
  );
};
