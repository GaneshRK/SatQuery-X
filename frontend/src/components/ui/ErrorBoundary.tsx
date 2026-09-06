"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error inside ErrorBoundary:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 text-center flex flex-col items-center justify-center min-h-[220px]">
          <div className="w-10 h-10 rounded-full bg-amber-950/50 border border-amber-800/60 flex items-center justify-center text-amber-400 mb-3">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <h4 className="text-sm font-semibold text-slate-200">
            {this.props.fallbackTitle || "Unable to render component"}
          </h4>
          <p className="text-xs text-slate-400 mt-1 max-w-sm">
            {this.state.error?.message || "An unexpected error occurred while displaying this surface."}
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            leftIcon={<RefreshCw className="w-3 h-3" />}
            onClick={() => this.setState({ hasError: false })}
          >
            Retry Render
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
