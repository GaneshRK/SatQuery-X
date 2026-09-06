"use client";

import React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "glass" | "subtle" | "interactive";
  padding?: "none" | "sm" | "md" | "lg";
}

export const Card: React.FC<CardProps> = ({
  children,
  variant = "glass",
  padding = "md",
  className = "",
  ...props
}) => {
  const variantStyles = {
    default: "bg-slate-900 border border-slate-800 text-slate-100",
    glass: "bg-slate-900/70 backdrop-blur-md border border-slate-800/80 text-slate-100 shadow-xl shadow-black/20",
    subtle: "bg-slate-950/40 border border-slate-800/50 text-slate-200",
    interactive:
      "bg-slate-900/70 backdrop-blur-md border border-slate-800 hover:border-slate-700 hover:bg-slate-900/90 text-slate-100 transition-all cursor-pointer shadow-lg hover:shadow-cyan-500/5",
  };

  const paddingStyles = {
    none: "p-0",
    sm: "p-3",
    md: "p-4",
    lg: "p-6",
  };

  return (
    <div
      className={`rounded-xl ${variantStyles[variant]} ${paddingStyles[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};
